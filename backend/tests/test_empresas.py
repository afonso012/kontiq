"""Painel e empresas-cliente pela API, contra PostgreSQL real."""
import random

from fastapi.testclient import TestClient

from app.empresas import servico as emp
from tests.test_auth import (  # noqa: F401  (fixtures reutilizadas)
    PASSWORD, cliente, enviados, limpar, nif_aleatorio, pytestmark, registar,
)
import pytest


@pytest.fixture
def mensagens(monkeypatch):
    caixa: list[dict] = []
    monkeypatch.setattr(emp, "enviar_sms", lambda numero, texto: caixa.append({"canal": "sms", "para": numero, "texto": texto}))
    monkeypatch.setattr(emp, "enviar_email", lambda para, assunto, titulo, pars, codigo=None:
                        caixa.append({"canal": "email", "para": para, "texto": " ".join(pars)}))
    return caixa


def gabinete_confirmado(cliente, enviados, limpar):
    r, email, nif = registar(cliente, limpar)
    assert r.status_code == 201, r.text
    assert cliente.post("/api/auth/email/confirmar", json={"codigo": enviados[-1]["codigo"]}).status_code == 200
    return email, nif


def telemovel():
    return "9" + random.choice("1236") + "".join(random.choice("0123456789") for _ in range(7))


def test_painel_vazio_e_primeira_empresa(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    p = cliente.get("/api/painel").json()
    assert p["empresas"] == [] and p["onboarding"] == {"empresas": False, "portal": False}
    assert p["totais"]["faturas"] == 0 and p["gabinete"]["nome"] == "Gabinete Teste"

    tel = telemovel()
    limpar[0].append(f"351{tel}@telemovel.local")
    nif = nif_aleatorio()
    r = cliente.post("/api/empresas", json={"nif": nif, "nome": "Mercearia Teste, Lda", "periodicidade_iva": "mensal",
                                            "contacto_nome": "Rui Teste", "telefone": tel, "convidar": True})
    assert r.status_code == 201, r.text
    assert mensagens[-1]["canal"] == "sms" and mensagens[-1]["para"] == "+351" + tel
    assert "Gabinete Teste" in mensagens[-1]["texto"] and "/portal" in mensagens[-1]["texto"]

    p = cliente.get("/api/painel").json()
    assert p["onboarding"] == {"empresas": True, "portal": True}
    e = p["empresas"][0]
    assert e["nome"] == "Mercearia Teste, Lda" and e["estado"] == "none" and e["portal"] is True
    assert e["periodicidade_iva"] == "mensal" and e["contacto"]["telefone"] == "+351" + tel

    # O mesmo NIF não entra duas vezes no gabinete.
    r = cliente.post("/api/empresas", json={"nif": nif, "nome": "Outra"})
    assert r.status_code == 409 and r.json()["campo"] == "nif"

    # O cliente convidado consegue entrar no portal com o código por SMS.
    portal = TestClient(cliente.app)
    assert portal.post("/api/portal/codigo", json={"canal": "sms", "destino": tel}).status_code == 202
    r = portal.post("/api/portal/entrar", json={"canal": "sms", "destino": tel, "codigo": enviados[-1]["codigo"]})
    assert r.status_code == 200 and r.json()["tipo"] == "portal"
    assert portal.get("/api/portal/resumo").json()["empresa"]["nome"] == "Mercearia Teste, Lda"
    # …e não entra no painel do gabinete.
    assert portal.get("/api/painel").status_code == 403


def test_validacoes(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    r = cliente.post("/api/empresas", json={"nif": "123456780", "nome": "X Lda"})
    assert r.status_code == 422 and r.json()["campo"] == "nif"
    r = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "X Lda", "telefone": "21 000 00 00"})
    assert r.status_code == 422 and r.json()["campo"] == "telefone"
    # Convidar sem forma de contacto não pode ser.
    r = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "X Lda", "contacto_nome": "Ana", "convidar": True})
    assert r.status_code == 422 and r.json()["codigo"] == "contacto_sem_meio"
    # Nada foi criado pelos pedidos recusados.
    assert cliente.get("/api/painel").json()["empresas"] == []


def test_editar_e_pedir_faturas(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    nif = nif_aleatorio()
    eid = cliente.post("/api/empresas", json={"nif": nif, "nome": "Oficina Teste"}).json()["id"]
    # Sem contacto não se pode pedir faturas.
    assert cliente.post(f"/api/empresas/{eid}/pedir-faturas", json={}).status_code == 422
    r = cliente.put(f"/api/empresas/{eid}", json={"nif": nif, "nome": "Oficina Teste, Lda",
                                                  "contacto_nome": "Ana Teste", "email": "ana@oficina-teste.pt"})
    assert r.status_code == 200 and r.json()["nome"] == "Oficina Teste, Lda"
    r = cliente.post(f"/api/empresas/{eid}/pedir-faturas", json={})
    assert r.status_code == 200 and r.json()["canal"] == "email"
    assert mensagens[-1]["para"] == "ana@oficina-teste.pt"
    assert cliente.post(f"/api/empresas/{eid}/pedir-faturas", json={}).json()["codigo"] == "pedido_recente"
    assert cliente.get("/api/painel").json()["empresas"][0]["pedido_em"] is not None


def test_gabinetes_nao_se_veem(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    eid = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Empresa do A"}).json()["id"]
    outro = TestClient(cliente.app)
    gabinete_confirmado(outro, enviados, limpar)
    assert outro.get("/api/painel").json()["empresas"] == []
    r = outro.put(f"/api/empresas/{eid}", json={"nif": nif_aleatorio(), "nome": "Roubada"})
    assert r.status_code == 404
    assert outro.post(f"/api/empresas/{eid}/convite").status_code == 404


def test_painel_demo_tem_numeros(cliente):
    """Com os dados de demonstração: totais e estados coerentes.

    Não exige um estado concreto (por exemplo, um duplicado por resolver): quem usa a
    demonstração muda-a, e os duplicados já são testados com dados próprios em test_faturas.
    """
    r = cliente.post("/api/auth/entrar", json={"email": "demo@faturas.local", "password": "demonstracao-2026"})
    if r.status_code != 200:
        pytest.skip("Sem dados de demonstração")
    p = cliente.get("/api/painel", params={"periodo": "2026-10"}).json()
    empresas = p["empresas"]
    assert len(empresas) >= 3 and p["totais"]["faturas"] == sum(e["faturas"] for e in empresas)
    for e in empresas:
        esperado = ("bad" if e["com_erro"] else "none" if not e["faturas"]
                    else "warn" if e["conferidas"] < e["faturas"] else "ok")
        assert e["estado"] == esperado, e["nome"]
    ordem = {"bad": 0, "warn": 1, "none": 2, "ok": 3}
    assert [ordem[e["estado"]] for e in empresas] == sorted(ordem[e["estado"]] for e in empresas)  # por gravidade
    ids = {e["id"] for e in empresas}
    assert all(a.get("empresa_id") in ids for a in p["atencao"] if a.get("empresa_id"))
