"""Autenticação de ponta a ponta pela API, contra PostgreSQL real.

Os códigos enviados por email/SMS são apanhados em memória em vez de enviados.
"""
import os
import random
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.auth import servico as svc
from app.core.seguranca import normalizar_telemovel, problema_password
from app.domain.nif import nif_valido

APP_URL = os.environ.get("DATABASE_URL")
DONO_URL = os.environ.get("MIGRATIONS_DATABASE_URL")
pytestmark = pytest.mark.skipif(not (APP_URL and DONO_URL), reason="Sem base de dados de teste")

PASSWORD = "Faturas-Seguras-2026"


@pytest.fixture
def enviados(monkeypatch):
    caixa: list[dict] = []

    def falso(finalidade, canal, destino, codigo, nome):
        caixa.append({"finalidade": finalidade, "canal": canal, "destino": destino, "codigo": codigo})
    monkeypatch.setattr(svc, "_enviar_codigo", falso)
    return caixa


@pytest.fixture
def cliente():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def limpar():
    emails, nifs = [], []
    yield emails, nifs
    eng = create_engine(DONO_URL)
    with eng.begin() as c:
        c.execute(text("DELETE FROM tentativas_login WHERE chave LIKE ANY(:p)"),
                  {"p": [f"%{e}%" for e in emails] or ["-"]})
        c.execute(text("DELETE FROM codigos_verificacao WHERE destino = ANY(:e)"), {"e": emails})
        c.execute(text("DELETE FROM utilizadores WHERE lower(email) = ANY(:e)"), {"e": emails})
        c.execute(text("DELETE FROM gabinetes WHERE nif = ANY(:n)"), {"n": nifs})
    eng.dispose()


def nif_aleatorio() -> str:
    while True:
        base = "5" + "".join(random.choice("0123456789") for _ in range(7))
        for d in "0123456789":
            if nif_valido(base + d):
                return base + d


def registar(cliente, limpar, email=None, nif=None):
    email = email or f"teste-{uuid.uuid4().hex[:8]}@exemplo.pt"
    nif = nif or nif_aleatorio()
    limpar[0].append(email); limpar[1].append(nif)
    r = cliente.post("/api/auth/registo", json={
        "nome": "Marta Teste", "email": email, "password": PASSWORD,
        "gabinete": {"nome": "Gabinete Teste", "nif": nif, "programa": "toconline", "dimensao": "21_50"}})
    return r, email, nif


# ---------------------------------------------------------------- unidades

def test_regras_password():
    assert problema_password("curta") is not None
    assert problema_password("aaaaaaaaaaaaaaaa") is not None
    assert problema_password("marta-faturas-2026", "marta@x.pt") is not None
    assert problema_password(PASSWORD, "marta@x.pt", "Marta Teste") is None


def test_telemovel():
    assert normalizar_telemovel("912 345 678") == "+351912345678"
    assert normalizar_telemovel("+351 912345678") == "+351912345678"
    assert normalizar_telemovel("00351932000000") == "+351932000000"
    assert normalizar_telemovel("212345678") is None


# ---------------------------------------------------------------- registo

def test_registo_completo(cliente, enviados, limpar):
    r, email, _ = registar(cliente, limpar)
    assert r.status_code == 201, r.text
    assert r.json()["utilizador"]["email_confirmado"] is False
    assert r.json()["papel"] == "dono"
    assert "pf_sessao" in r.cookies
    # Sem email confirmado, o painel recusa.
    assert cliente.get("/api/painel/resumo").json()["codigo"] == "email_por_confirmar"
    codigo = enviados[-1]["codigo"]
    errado = "000000" if codigo != "000000" else "111111"
    assert cliente.post("/api/auth/email/confirmar", json={"codigo": errado}).status_code == 400
    r = cliente.post("/api/auth/email/confirmar", json={"codigo": codigo})
    assert r.status_code == 200 and r.json()["utilizador"]["email_confirmado"] is True
    resumo = cliente.get("/api/painel/resumo").json()
    assert resumo["gabinete"]["nome"] == "Gabinete Teste" and resumo["empresas"] == 0


def test_registo_recusa_duplicados_e_dados_maus(cliente, enviados, limpar):
    r, email, nif = registar(cliente, limpar)
    assert r.status_code == 201
    novo = TestClient(cliente.app)
    r = novo.post("/api/auth/registo/validar-conta", json={"nome": "Outra", "email": email.upper(), "password": PASSWORD})
    assert r.status_code == 409 and r.json()["campo"] == "email"
    r, *_ = registar(novo, limpar, nif=nif)
    assert r.status_code == 409 and r.json()["campo"] == "nif"
    r, *_ = registar(novo, limpar, nif="123456780")
    assert r.status_code == 422 and r.json()["campo"] == "nif"


def test_reenviar_respeita_espera(cliente, enviados, limpar):
    registar(cliente, limpar)
    r = cliente.post("/api/auth/email/reenviar")
    assert r.status_code == 429 and r.json()["codigo"] == "espere"


# ---------------------------------------------------------------- entrar

def test_entrar_sair(cliente, enviados, limpar):
    _, email, _ = registar(cliente, limpar)
    cliente.post("/api/auth/sair")
    assert cliente.get("/api/auth/eu").status_code == 401
    r = cliente.post("/api/auth/entrar", json={"email": email, "password": "errada-mas-comprida"})
    assert r.status_code == 401 and r.json()["mensagem"] == "Email ou palavra-passe errados."
    r = cliente.post("/api/auth/entrar", json={"email": email.upper(), "password": PASSWORD, "manter": False})
    assert r.status_code == 200 and r.json()["gabinete"]["nome"] == "Gabinete Teste"
    assert cliente.get("/api/auth/eu").status_code == 200
    cliente.post("/api/auth/sair")
    assert cliente.get("/api/auth/eu").status_code == 401


def test_email_inexistente_responde_igual(cliente, enviados):
    r = cliente.post("/api/auth/entrar", json={"email": f"ninguem-{uuid.uuid4().hex[:6]}@exemplo.pt", "password": PASSWORD})
    assert r.status_code == 401 and r.json()["mensagem"] == "Email ou palavra-passe errados."


def test_trava_depois_de_muitas_falhas(cliente, enviados, limpar):
    _, email, _ = registar(cliente, limpar)
    for _ in range(svc.FALHAS_POR_CONTA):
        cliente.post("/api/auth/entrar", json={"email": email, "password": "errada-mas-comprida"})
    r = cliente.post("/api/auth/entrar", json={"email": email, "password": PASSWORD})
    assert r.status_code == 429


def test_repor_password(cliente, enviados, limpar):
    _, email, _ = registar(cliente, limpar)
    antigo = TestClient(cliente.app, cookies=dict(cliente.cookies))
    assert cliente.post("/api/auth/password/pedir", json={"email": email}).status_code == 202
    codigo = [e for e in enviados if e["finalidade"] == "repor_password"][-1]["codigo"]
    novo = "Outra-Palavra-Segura-99"
    r = cliente.post("/api/auth/password/repor", json={"email": email, "codigo": codigo, "password": novo})
    assert r.status_code == 200, r.text
    assert r.json()["utilizador"]["email_confirmado"] is True
    # As outras sessões terminam; a palavra-passe antiga deixa de servir.
    assert antigo.get("/api/auth/eu").status_code == 401
    assert cliente.post("/api/auth/entrar", json={"email": email, "password": PASSWORD}).status_code == 401
    assert cliente.post("/api/auth/entrar", json={"email": email, "password": novo}).status_code == 200


def test_codigo_bloqueia_apos_5_tentativas(cliente, enviados, limpar):
    _, email, _ = registar(cliente, limpar)
    codigo = enviados[-1]["codigo"]
    errado = "000000" if codigo != "000000" else "111111"
    for _ in range(svc.TENTATIVAS_POR_CODIGO):
        cliente.post("/api/auth/email/confirmar", json={"codigo": errado})
    r = cliente.post("/api/auth/email/confirmar", json={"codigo": codigo})
    assert r.status_code == 400  # o código certo já não serve


# ---------------------------------------------------------------- portal

def test_portal_por_sms_com_conta_demo(cliente, enviados):
    from app.demo import DEMO_CLIENTE, semear
    semear()
    tel = DEMO_CLIENTE[2]
    assert cliente.post("/api/portal/codigo", json={"canal": "sms", "destino": "912 345 678"}).status_code == 202
    codigo = [e for e in enviados if e["destino"] == tel][-1]["codigo"]
    r = cliente.post("/api/portal/entrar", json={"canal": "sms", "destino": "912345678", "codigo": codigo})
    assert r.status_code == 200 and r.json()["tipo"] == "portal"
    resumo = cliente.get("/api/portal/resumo").json()
    assert resumo["empresa"]["nome"].startswith("Restaurante O Faroleiro")
    # Uma sessão do portal não abre o painel do gabinete.
    assert cliente.get("/api/painel/resumo").status_code == 403


def test_portal_numero_desconhecido_responde_igual(cliente, enviados):
    r = cliente.post("/api/portal/codigo", json={"canal": "sms", "destino": "939 999 999"})
    assert r.status_code == 202 and enviados == []
    r = cliente.post("/api/portal/codigo", json={"canal": "sms", "destino": "123"})
    assert r.status_code == 422
