"""Dúvidas sobre faturas: o gabinete pergunta, o cliente responde no portal."""
import pytest
from fastapi.testclient import TestClient

from app.faturas import duvidas as dv
from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens  # noqa: F401
from tests.test_faturas import imagem_com_qr, qr_texto
from tests.test_portal import cliente_no_portal


@pytest.fixture
def avisos(monkeypatch):
    caixa: list[dict] = []
    monkeypatch.setattr(dv, "enviar_sms", lambda numero, texto: caixa.append({"canal": "sms", "para": numero, "texto": texto}))
    monkeypatch.setattr(dv, "enviar_email", lambda para, assunto, titulo, pars, codigo=None:
                        caixa.append({"canal": "email", "para": para, "texto": " ".join(pars)}))
    return caixa


def _fatura_do_portal(portal, nif, numero="FT 9/1"):
    foto = imagem_com_qr(qr_texto(nif, numero), "JPEG")
    r = portal.post("/api/portal/documentos", files=[("ficheiros", ("IMG.jpg", foto, "image/jpeg"))])
    assert r.status_code == 200, r.text


def test_pergunta_resposta_e_resolver(cliente, enviados, limpar, mensagens, avisos):
    portal, eid, nif = cliente_no_portal(cliente, enviados, limpar)
    _fatura_do_portal(portal, nif)
    fid = cliente.get(f"/api/empresas/{eid}/faturas").json()["faturas"][0]["id"]

    assert cliente.post(f"/api/faturas/{fid}/duvida", json={"texto": "   "}).status_code == 422
    r = cliente.post(f"/api/faturas/{fid}/duvida", json={"texto": "Esta  compra é da   empresa ou pessoal?"})
    assert r.status_code == 200, r.text
    assert r.json()["avisado"] == "sms" and r.json()["duvida"] == "pergunta"
    assert len(avisos) == 1 and "FT 9/1" in avisos[0]["texto"] and "Esta compra é da empresa ou pessoal?" in avisos[0]["texto"]
    # Uma segunda mensagem antes da resposta não volta a avisar.
    assert cliente.post(f"/api/faturas/{fid}/duvida", json={"texto": "É urgente."}).json()["avisado"] is None
    assert len(avisos) == 1

    lista = cliente.get(f"/api/empresas/{eid}/faturas").json()["faturas"]
    assert lista[0]["duvida"] == "pergunta"

    ini = portal.get("/api/portal/inicio").json()
    assert len(ini["duvidas"]) == 1
    d = ini["duvidas"][0]
    assert d["numero"] == "FT 9/1" and [m["lado"] for m in d["mensagens"]] == ["gabinete", "gabinete"]
    assert portal.get(f"/api/portal/documentos/{d['documento']['id']}/pagina/1").headers["content-type"] == "image/png"

    r = portal.post(f"/api/portal/duvidas/{fid}", json={"texto": "É da empresa, para o escritório."})
    assert r.status_code == 200 and r.json()["estado"] == "resposta"

    p = cliente.get("/api/painel").json()
    item = next(a for a in p["atencao"] if a["codigo"] == "cliente_respondeu")
    assert item["fatura_id"] == fid and item["empresa_id"] == eid
    det = cliente.get(f"/api/faturas/{fid}").json()
    assert det["duvida"] == "resposta" and det["mensagens"][-1]["lado"] == "cliente"
    assert det["mensagens"][-1]["autor"] == "Rui Portal"

    assert cliente.post(f"/api/faturas/{fid}/duvida/resolver").json()["duvida"] is None
    assert not any(a["codigo"] == "cliente_respondeu" for a in cliente.get("/api/painel").json()["atencao"])
    assert portal.get("/api/portal/inicio").json()["duvidas"] == []
    assert portal.post(f"/api/portal/duvidas/{fid}", json={"texto": "Mais uma coisa"}).status_code == 409

    # Reabrir avisa outra vez.
    cliente.post(f"/api/faturas/{fid}/duvida", json={"texto": "Afinal falta o NIF."})
    assert len(avisos) == 2


def test_cliente_so_responde_a_propria_empresa(cliente, enviados, limpar, mensagens, avisos):
    portal, eid, nif = cliente_no_portal(cliente, enviados, limpar)
    outra = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Outra", "email": "outra@teste.local"}).json()["id"]
    foto = imagem_com_qr(qr_texto("123456789", "FT 5/5"), "PDF")
    cliente.post(f"/api/empresas/{outra}/documentos", files=[("ficheiros", ("x.pdf", foto, "application/pdf"))])
    f_outra = cliente.get(f"/api/empresas/{outra}/faturas").json()["faturas"][0]
    r = cliente.post(f"/api/faturas/{f_outra['id']}/duvida", json={"texto": "Pergunta"})
    assert r.json()["avisado"] == "email"
    det = cliente.get(f"/api/faturas/{f_outra['id']}").json()
    assert portal.post(f"/api/portal/duvidas/{f_outra['id']}", json={"texto": "Olá"}).status_code == 404
    assert portal.get(f"/api/portal/documentos/{det['documento']['id']}/pagina/1").status_code == 404
    assert portal.get("/api/portal/inicio").json()["duvidas"] == []
    # O portal não escreve como gabinete.
    assert portal.post(f"/api/faturas/{f_outra['id']}/duvida", json={"texto": "x"}).status_code == 403


def test_empresa_sem_contacto(cliente, enviados, limpar, avisos):
    gabinete_confirmado(cliente, enviados, limpar)
    eid = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Sem Contacto"}).json()["id"]
    foto = imagem_com_qr(qr_texto("123456789", "FT 6/6"), "PDF")
    cliente.post(f"/api/empresas/{eid}/documentos", files=[("ficheiros", ("x.pdf", foto, "application/pdf"))])
    fid = cliente.get(f"/api/empresas/{eid}/faturas").json()["faturas"][0]["id"]
    r = cliente.post(f"/api/faturas/{fid}/duvida", json={"texto": "Pergunta"})
    assert r.status_code == 422 and r.json()["codigo"] == "contacto_sem_meio"
