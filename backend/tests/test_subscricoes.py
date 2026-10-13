"""Subscrições: teste grátis, escolher plano, limites, cancelar e atrasos."""
from sqlalchemy import create_engine, text

from app.equipa import servico as eq
from tests.test_auth import DONO_URL, cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado
from tests.test_faturas import imagem_com_qr, qr_texto


def _sql(q: str, **p):
    eng = create_engine(DONO_URL)
    with eng.begin() as c:
        c.execute(text(q), p)
    eng.dispose()


def _gid(cliente) -> str:
    return cliente.get("/api/auth/eu").json()["gabinete"]["id"]


def _pagar(cliente, plano, ciclo="mensal", sucesso=True):
    r = cliente.post("/api/subscricao/pagamentos", json={"plano": plano, "ciclo": ciclo})
    assert r.status_code == 201, r.text
    pid = r.json()["pagamento"]
    assert r.json()["url"] == f"/subscricao/pagamento/{pid}"
    assert cliente.get(f"/api/subscricao/pagamentos/{pid}").json()["estado"] == "pendente"
    return cliente.post(f"/api/subscricao/pagamentos/{pid}/simular", json={"sucesso": sucesso})


def test_teste_gratis_e_pagar(cliente, enviados, limpar):
    gabinete_confirmado(cliente, enviados, limpar)
    d = cliente.get("/api/subscricao").json()
    assert d["estado"] == "teste" and d["plano"] == "gabinete" and d["dias"] == 30 and d["pode_trabalhar"]
    assert [p["id"] for p in d["planos"]] == ["arranque", "gabinete", "pro"]
    assert d["planos"][0]["mensal"] == "29 €" and d["planos"][2]["anual"] == "1 490 €"
    assert d["limites"] == {"empresas": 40, "pessoas": 5} and d["pode_gerir"]
    assert cliente.get("/api/auth/eu").json()["subscricao"]["estado"] == "teste"

    falhou = _pagar(cliente, "arranque", sucesso=False)
    assert falhou.json()["estado"] == "falhado"
    assert cliente.get("/api/subscricao").json()["estado"] == "teste"

    r = _pagar(cliente, "arranque")
    assert r.status_code == 200 and r.json()["estado"] == "pago" and r.json()["total"] == "35,67 €"
    d = cliente.get("/api/subscricao").json()
    assert d["estado"] == "ativa" and d["plano"] == "arranque" and d["limites"] == {"empresas": 10, "pessoas": 2}
    assert [p["estado"] for p in d["pagamentos"]] == ["pago", "falhado"]
    assert cliente.post("/api/subscricao/pagamentos", json={"plano": "arranque", "ciclo": "mensal"}).status_code == 409
    assert cliente.post("/api/subscricao/pagamentos", json={"plano": "ouro"}).status_code == 422

    anual = _pagar(cliente, "pro", "anual").json()
    assert anual["total"] == "1 832,70 €"
    d = cliente.get("/api/subscricao").json()
    assert d["plano"] == "pro" and d["ciclo"] == "anual" and d["limites"]["pessoas"] is None


def test_limites_de_empresas_e_pessoas(cliente, enviados, limpar, monkeypatch):
    monkeypatch.setattr(eq, "enviar_email", lambda *a, **k: None)
    gabinete_confirmado(cliente, enviados, limpar)
    for i in range(11):
        assert cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": f"Empresa {i}"}).status_code == 201
    # Com 11 empresas não pode descer para o Arranque (10).
    r = cliente.post("/api/subscricao/pagamentos", json={"plano": "arranque"})
    assert r.status_code == 409 and r.json()["codigo"] == "excede_empresas"
    assert next(p for p in cliente.get("/api/subscricao").json()["planos"] if p["id"] == "arranque")["cabe"] is False

    _sql("UPDATE subscricoes SET limite_empresas = 11 WHERE gabinete_id = :g", g=_gid(cliente))
    r = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "A mais"})
    assert r.status_code == 402 and r.json()["codigo"] == "limite_empresas"

    # Pessoas: o plano Gabinete inclui 5 (dono + 4 convites).
    for i in range(4):
        email = f"p{i}-{nif_aleatorio()}@teste.local"
        limpar[0].append(email)
        assert cliente.post("/api/equipa/convites", json={"email": email}).status_code == 201
    r = cliente.post("/api/equipa/convites", json={"email": "sexta@teste.local"})
    assert r.status_code == 402 and r.json()["codigo"] == "limite_pessoas"


def test_teste_expirado_bloqueia_trabalho(cliente, enviados, limpar):
    gabinete_confirmado(cliente, enviados, limpar)
    eid = cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Antes"}).json()["id"]
    _sql("UPDATE subscricoes SET fim_teste = now() - interval '1 day' WHERE gabinete_id = :g", g=_gid(cliente))
    eu = cliente.get("/api/auth/eu").json()["subscricao"]
    assert eu["estado"] == "expirada" and not eu["pode_trabalhar"] and "terminou" in eu["aviso"]
    pdf = imagem_com_qr(qr_texto(nif_aleatorio(), "FT 1/1"), "PDF")
    r = cliente.post(f"/api/empresas/{eid}/documentos", files=[("ficheiros", ("a.pdf", pdf, "application/pdf"))])
    assert r.status_code == 402 and r.json()["codigo"] == "subscricao_inativa"
    assert cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Depois"}).status_code == 402
    assert cliente.get("/api/painel").status_code == 200  # consultar continua
    assert _pagar(cliente, "gabinete").status_code == 200
    assert cliente.get("/api/auth/eu").json()["subscricao"]["pode_trabalhar"]


def test_cancelar_atraso_e_suspensao(cliente, enviados, limpar):
    gabinete_confirmado(cliente, enviados, limpar)
    assert cliente.post("/api/subscricao/cancelar").status_code == 409  # em teste não há nada a cancelar
    _pagar(cliente, "gabinete")
    d = cliente.post("/api/subscricao/cancelar").json()
    assert d["cancelar_no_fim"] and d["estado"] == "ativa" and "não será renovada" in d["aviso"]
    assert cliente.post("/api/subscricao/retomar").json()["cancelar_no_fim"] is False
    g = _gid(cliente)

    _sql("UPDATE subscricoes SET proxima_renovacao = now() - interval '2 days' WHERE gabinete_id = :g", g=g)
    d = cliente.get("/api/subscricao").json()
    assert d["estado"] == "em_atraso" and d["pode_trabalhar"] and d["dias"] == 5
    _sql("UPDATE subscricoes SET proxima_renovacao = now() - interval '8 days' WHERE gabinete_id = :g", g=g)
    d = cliente.get("/api/subscricao").json()
    assert d["estado"] == "suspensa" and not d["pode_trabalhar"]

    _pagar(cliente, "gabinete")
    cliente.post("/api/subscricao/cancelar")
    _sql("UPDATE subscricoes SET proxima_renovacao = now() - interval '1 hour' WHERE gabinete_id = :g", g=g)
    d = cliente.get("/api/subscricao").json()
    assert d["estado"] == "cancelada" and not d["pode_trabalhar"]
