"""Portal do cliente: entrar, enviar faturas e ver o estado."""
from fastapi.testclient import TestClient

from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens, telemovel  # noqa: F401
from tests.test_faturas import MES, carregar, imagem_com_qr, qr_texto


def cliente_no_portal(cliente, enviados, limpar):
    gabinete_confirmado(cliente, enviados, limpar)
    tel = telemovel()
    limpar[0].append(f"351{tel}@telemovel.local")
    nif = nif_aleatorio()
    eid = cliente.post("/api/empresas", json={"nif": nif, "nome": "Cliente Portal, Lda", "contacto_nome": "Rui Portal",
                                              "telefone": tel, "convidar": True}).json()["id"]
    portal = TestClient(cliente.app)
    assert portal.post("/api/portal/codigo", json={"canal": "sms", "destino": tel}).status_code == 202
    r = portal.post("/api/portal/entrar", json={"canal": "sms", "destino": tel, "codigo": enviados[-1]["codigo"]})
    assert r.status_code == 200
    return portal, eid, nif


def test_enviar_e_ver_estado(cliente, enviados, limpar, mensagens):
    portal, eid, nif = cliente_no_portal(cliente, enviados, limpar)
    ini = portal.get("/api/portal/inicio").json()
    assert ini["empresa"]["nome"] == "Cliente Portal, Lda" and ini["enviados"] == [] and ini["pedido"] is None

    foto = imagem_com_qr(qr_texto(nif, "FT 7/1"), "JPEG")
    r = portal.post("/api/portal/documentos", files=[("ficheiros", ("IMG_0001.jpg", foto, "image/jpeg"))])
    assert r.status_code == 200 and r.json()["resultados"][0]["ok"] is True
    again = portal.post("/api/portal/documentos", files=[("ficheiros", ("IMG_0001.jpg", foto, "image/jpeg"))]).json()
    assert again["resultados"][0]["repetido"] is True

    ini = portal.get("/api/portal/inicio").json()
    assert ini["enviados_mes"] == 1 and ini["enviados"][0]["estado"] == "recebida" and ini["enviados"][0]["canal"] == "portal"

    # O gabinete vê-a por conferir; confere; o cliente vê "tratada".
    lista = cliente.get(f"/api/empresas/{eid}/faturas", params={"periodo": MES}).json()
    fid = lista["faturas"][0]["id"]
    assert cliente.get(f"/api/faturas/{fid}").json()["documento"]["canal"] == "portal"
    op = cliente.get("/api/classificacao").json()
    cat = next(c for c in op["categorias"] if c["conta"])
    d = cliente.get(f"/api/faturas/{fid}").json()
    corpo = {"fornecedor": "Papelaria Teste", "nif": d["fornecedor"]["nif"], "tipo_documento": "FT", "numero": d["numero"],
             "data": d["data"], "total": d["total"], "linhas": [{"taxa": 23, "base": "77.90", "iva": "17.92"}],
             "categoria_id": cat["id"], "conta": cat["conta"], "tratamento_iva": "dedutivel"}
    assert cliente.post(f"/api/faturas/{fid}/conferir", json={"dados": corpo}).status_code == 200
    assert portal.get("/api/portal/inicio").json()["enviados"][0]["estado"] == "tratada"

    # O portal não abre as áreas do gabinete.
    assert portal.get(f"/api/faturas/{fid}").status_code == 403
    assert portal.get("/api/painel").status_code == 403


def test_so_ve_a_propria_empresa_e_pedidos(cliente, enviados, limpar, mensagens):
    portal, eid, nif = cliente_no_portal(cliente, enviados, limpar)
    # Outra empresa do mesmo gabinete com uma fatura: o cliente não a vê.
    outra, nif2 = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Outra"}).json()["id"], None
    carregar(cliente, outra, ("x.pdf", imagem_com_qr(qr_texto("123456789", "FT 8/1"), "PDF")))
    assert portal.get("/api/portal/inicio").json()["enviados"] == []
    # Um pedido do gabinete aparece até o cliente enviar alguma coisa.
    assert cliente.post(f"/api/empresas/{eid}/pedir-faturas", json={}).status_code == 200
    assert portal.get("/api/portal/inicio").json()["pedido"] is not None
    portal.post("/api/portal/documentos", files=[("ficheiros", ("f.pdf", imagem_com_qr(qr_texto(nif, "FT 9/9"), "PDF"), "application/pdf"))])
    assert portal.get("/api/portal/inicio").json()["pedido"] is None
