"""Resumo do IVA para a declaração periódica."""
import io

from openpyxl import load_workbook

from app.faturas import iva as iva_svc
from tests.test_auth import cliente, enviados, limpar, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens  # noqa: F401
from tests.test_faturas import MES, carregar, criar_empresa, imagem_com_qr, qr_texto
from datetime import date


def _conferir(cliente, fid, conta, tratamento, tipo="FT"):
    d = cliente.get(f"/api/faturas/{fid}").json()
    corpo = {"fornecedor": "F", "nif": d["fornecedor"]["nif"], "tipo_documento": tipo, "numero": d["numero"], "data": d["data"],
             "total": d["total"], "linhas": [{"taxa": 23, "base": "77.90", "iva": "17.92"}], "categoria_id": None,
             "conta": conta, "tratamento_iva": tratamento}
    r = cliente.post(f"/api/faturas/{fid}/conferir", json={"dados": corpo})
    assert r.status_code == 200, r.text


def test_resumo_e_campos(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    eid, nif = criar_empresa(cliente)
    res = carregar(cliente, eid, *[(f"{i}.pdf", imagem_com_qr(qr_texto(nif, f"FT 9/{i}"), "PDF")) for i in range(4)])
    _conferir(cliente, res[0]["fatura_id"], "6222", "dedutivel")      # campo 24
    _conferir(cliente, res[1]["fatura_id"], "311", "dedutivel")       # existências normal → 22
    _conferir(cliente, res[2]["fatura_id"], "6242", "dedutivel_50")   # 50% → 24
    # a quarta fica por conferir

    r = cliente.get(f"/api/empresas/{eid}/iva", params={"periodo": MES, "tipo": "mes"}).json()
    assert r["faturas"] == 3 and r["por_conferir"] == 1
    campos = {c["campo"]: c["valor_n"] for c in r["campos"]}
    assert campos == {"20": 0, "21": 0, "23": 0, "22": 17.92, "24": 26.88}
    assert r["totais"]["dedutivel_n"] == 44.80 and r["totais"]["iva_n"] == 53.76 and r["totais"]["nao_dedutivel"] == "8,96 €"
    assert {t["id"] for t in r["tratamentos"]} == {"dedutivel", "dedutivel_50"}
    assert [c["conta"] for c in r["contas"]] == ["311", "6222", "6242"]
    assert r["taxas"][0]["espaco"] == "Continente" and r["taxas"][0]["base_n"] == 233.70

    tri = cliente.get(f"/api/empresas/{eid}/iva", params={"periodo": MES, "tipo": "trimestre"}).json()
    assert "trimestre" in tri["periodo_txt"] and tri["faturas"] == 3
    x = cliente.get(f"/api/empresas/{eid}/iva.xlsx", params={"periodo": MES, "tipo": "mes"})
    assert x.status_code == 200 and "attachment" in x.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(x.content)).active
    assert any(r[0] == "24" and r[2] == 26.88 for r in ws.iter_rows(values_only=True))
    assert cliente.get(f"/api/empresas/{eid}/iva", params={"tipo": "ano"}).status_code == 422


def test_campos_e_trimestres():
    assert iva_svc._campo("432", "normal") == "20" and iva_svc._campo("3121", "reduzida") == "21"
    assert iva_svc._campo("32", "intermedia") == "23" and iva_svc._campo("6221", "reduzida") == "24"
    assert iva_svc.intervalo(date(2026, 11, 1), "trimestre")[:2] == (date(2026, 10, 1), date(2027, 1, 1))
    assert iva_svc.intervalo(date(2026, 5, 1), "trimestre")[2] == "2.º trimestre de 2026"
