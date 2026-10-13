"""Lista de todas as faturas do gabinete e página de pedidos aos clientes."""
from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens, telemovel  # noqa: F401
from tests.test_faturas import MES, carregar, imagem_com_qr, qr_texto


def test_todas_as_faturas_filtros_e_pesquisa(cliente, enviados, limpar):
    gabinete_confirmado(cliente, enviados, limpar)
    a = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Alfa Lda"}).json()
    b = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Beta SA"}).json()
    nif_a = cliente.get(f"/api/empresas/{a['id']}/faturas").json()["empresa"]["nif"]
    nif_b = cliente.get(f"/api/empresas/{b['id']}/faturas").json()["empresa"]["nif"]
    carregar(cliente, a["id"], ("1.pdf", imagem_com_qr(qr_texto(nif_a, "FT 1/1"), "PDF")))
    carregar(cliente, a["id"], ("2.pdf", imagem_com_qr(qr_texto(nif_a, "FT 1/1"), "JPEG")))  # duplicado
    carregar(cliente, b["id"], ("3.pdf", imagem_com_qr(qr_texto(nif_b, "FT 9/9"), "PDF")))

    d = cliente.get("/api/faturas", params={"periodo": MES}).json()
    assert d["total"] == 3 and d["contagens"]["todas"] == 3 and d["contagens"]["problemas"] == 1
    assert {f["empresa"]["nome"] for f in d["faturas"]} == {"Alfa Lda", "Beta SA"}
    assert [e["nome"] for e in d["empresas"]] == ["Alfa Lda", "Beta SA"]

    assert cliente.get("/api/faturas", params={"periodo": MES, "filtro": "problemas"}).json()["total"] == 1
    assert cliente.get("/api/faturas", params={"periodo": MES, "q": "beta"}).json()["total"] == 1
    assert cliente.get("/api/faturas", params={"periodo": MES, "q": "FT 9"}).json()["faturas"][0]["numero"] == "FT 9/9"
    assert cliente.get("/api/faturas", params={"periodo": MES, "q": nif_b[:5]}).json()["total"] == 1
    assert cliente.get("/api/faturas", params={"periodo": MES, "empresa": a["id"]}).json()["total"] == 2
    assert cliente.get("/api/faturas", params={"periodo": MES, "filtro": "inventado"}).status_code == 422
    assert cliente.get("/api/faturas", params={"periodo": "2001-01"}).json()["total"] == 0


def test_pedidos_em_falta_e_pedir_a_todas(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    tel = telemovel()
    limpar[0].append(f"351{tel}@telemovel.local")
    cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Com SMS", "contacto_nome": "Ana", "telefone": tel})
    cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Com Email", "email": "c@teste.local"})
    cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Sem Contacto"})

    d = cliente.get("/api/pedidos").json()
    assert d["contagens"]["em_falta"] == 3 and d["pedidos"] == [] and d["duvidas"] == []

    r = cliente.post("/api/pedidos/todas", json={}).json()
    assert sorted(e["canal"] for e in r["enviados"]) == ["email", "sms"]
    assert r["ignoradas"] == [{"nome": "Sem Contacto", "motivo": "sem telemóvel nem email"}]
    assert len(mensagens) == 2

    d = cliente.get("/api/pedidos").json()
    assert len(d["pedidos"]) == 2 and not any(p["respondido"] for p in d["pedidos"])
    assert all(e["pedido_em"] for e in d["em_falta"] if e["meio"])
    # Pedir outra vez logo a seguir não volta a enviar.
    r = cliente.post("/api/pedidos/todas", json={}).json()
    assert r["enviados"] == [] and len(r["ignoradas"]) == 3 and len(mensagens) == 2
