"""Equipa do gabinete: convidar, aceitar, papéis e remoção."""
import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.equipa import servico as eq
from tests.test_auth import cliente, enviados, limpar, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado

PASS = "uma-frase-bem-comprida-2026"


@pytest.fixture
def correio(monkeypatch):
    caixa: list[dict] = []
    monkeypatch.setattr(eq, "enviar_email", lambda para, assunto, titulo, pars, codigo=None:
                        caixa.append({"para": para, "assunto": assunto, "texto": " ".join(pars)}))
    return caixa


def _token(msg: dict) -> str:
    return re.search(r"/convite/([\w-]+)", msg["texto"]).group(1)


def _convidar(cliente, limpar, correio, papel="colaborador"):
    email = f"colega-{uuid.uuid4().hex[:8]}@teste.local"
    limpar[0].append(email)
    r = cliente.post("/api/equipa/convites", json={"email": email.upper(), "papel": papel})
    assert r.status_code == 201, r.text
    assert correio[-1]["para"] == email
    return email, _token(correio[-1])


def test_convidar_e_aceitar_conta_nova(cliente, enviados, limpar, correio):
    gabinete_confirmado(cliente, enviados, limpar)
    eq_ = cliente.get("/api/equipa").json()
    assert eq_["eu"]["papel"] == "dono" and eq_["eu"]["pode_gerir"] and len(eq_["membros"]) == 1

    email, token = _convidar(cliente, limpar, correio)
    assert [c["email"] for c in cliente.get("/api/equipa").json()["convites"]] == [email]

    novo = TestClient(cliente.app)
    v = novo.get(f"/api/convites/{token}").json()
    assert v["gabinete"] == "Gabinete Teste" and v["email"] == email and v["conta_existe"] is False
    assert novo.post(f"/api/convites/{token}/aceitar", json={"nome": "A", "password": PASS}).status_code == 422
    assert novo.post(f"/api/convites/{token}/aceitar", json={"nome": "Ana Colega", "password": "curta"}).status_code == 422
    r = novo.post(f"/api/convites/{token}/aceitar", json={"nome": "Ana Colega", "password": PASS})
    assert r.status_code == 200, r.text
    eu = novo.get("/api/auth/eu").json()
    assert eu["tipo"] == "gabinete" and eu["papel"] == "colaborador" and eu["utilizador"]["email_confirmado"]
    assert novo.get("/api/painel").status_code == 200

    # O convite já não serve e saiu da lista de pendentes.
    assert novo.get(f"/api/convites/{token}").status_code == 410
    lista = cliente.get("/api/equipa").json()
    assert lista["convites"] == [] and len(lista["membros"]) == 2

    # Um colaborador vê a equipa mas não a gere.
    v2 = novo.get("/api/equipa").json()
    assert v2["eu"]["pode_gerir"] is False
    assert novo.post("/api/equipa/convites", json={"email": "x@teste.local"}).status_code == 403

    # Pode entrar depois com email e palavra-passe.
    outro = TestClient(cliente.app)
    assert outro.post("/api/auth/entrar", json={"email": email, "password": PASS}).status_code == 200


def test_papeis_e_remover(cliente, enviados, limpar, correio):
    gabinete_confirmado(cliente, enviados, limpar)
    email, token = _convidar(cliente, limpar, correio)
    novo = TestClient(cliente.app)
    novo.post(f"/api/convites/{token}/aceitar", json={"nome": "Rui Colega", "password": PASS})
    membros = cliente.get("/api/equipa").json()["membros"]
    dono = next(m for m in membros if m["papel"] == "dono")
    colega = next(m for m in membros if m["email"] == email)

    assert cliente.put(f"/api/equipa/membros/{dono['id']}", json={"papel": "colaborador"}).status_code == 409
    assert cliente.delete(f"/api/equipa/membros/{dono['id']}").status_code == 409
    assert cliente.put(f"/api/equipa/membros/{colega['id']}", json={"papel": "dono"}).status_code == 422
    assert cliente.put(f"/api/equipa/membros/{colega['id']}", json={"papel": "admin"}).status_code == 200
    assert novo.get("/api/equipa").json()["eu"]["pode_gerir"] is True

    # Removido: a sessão dele termina logo.
    assert cliente.delete(f"/api/equipa/membros/{colega['id']}").status_code == 200
    assert novo.get("/api/painel").status_code == 401
    assert len(cliente.get("/api/equipa").json()["membros"]) == 1


def test_convites_repetidos_cancelar_e_reenviar(cliente, enviados, limpar, correio):
    email_dono, _ = gabinete_confirmado(cliente, enviados, limpar)
    assert cliente.post("/api/equipa/convites", json={"email": email_dono}).status_code == 409
    assert cliente.post("/api/equipa/convites", json={"email": "nao-e-email"}).status_code == 422
    assert cliente.post("/api/equipa/convites", json={"email": "a@b.pt", "papel": "dono"}).status_code == 422

    email, t1 = _convidar(cliente, limpar, correio)
    t2 = _token(cliente.post("/api/equipa/convites", json={"email": email}) and correio[-1])
    assert cliente.get(f"/api/convites/{t1}").status_code == 410  # o novo substitui o antigo
    cid = cliente.get("/api/equipa").json()["convites"][0]["id"]
    assert cliente.post(f"/api/equipa/convites/{cid}/reenviar").status_code == 200
    t3 = _token(correio[-1])
    assert cliente.get(f"/api/convites/{t2}").status_code == 404 and cliente.get(f"/api/convites/{t3}").status_code == 200
    assert cliente.delete(f"/api/equipa/convites/{cid}").status_code == 200
    assert cliente.get(f"/api/convites/{t3}").status_code == 410
    assert cliente.get("/api/equipa").json()["convites"] == []
    assert cliente.get("/api/convites/inventado").status_code == 404
