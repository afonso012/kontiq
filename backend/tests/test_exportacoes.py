"""Exportar faturas conferidas: Excel, CSV, ZIP, bloqueio e desfazer."""
import csv
import io
import zipfile

from openpyxl import load_workbook

from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens  # noqa: F401
from tests.test_faturas import MES, carregar, criar_empresa, imagem_com_qr, qr_texto


def preparar(cliente, enviados, limpar):
    gabinete_confirmado(cliente, enviados, limpar)
    eid, nif = criar_empresa(cliente)
    res = carregar(cliente, eid, ("a.pdf", imagem_com_qr(qr_texto(nif, "FT 5/1"), "PDF")),
                   ("b.pdf", imagem_com_qr(qr_texto(nif, "FT 5/2"), "PDF")))
    op = cliente.get("/api/classificacao").json()
    cat = next(c for c in op["categorias"] if c["conta"])
    for r in res:
        d = cliente.get(f"/api/faturas/{r['fatura_id']}").json()
        corpo = {"fornecedor": "Papelaria Teste, Lda", "nif": d["fornecedor"]["nif"], "tipo_documento": "FT", "numero": d["numero"],
                 "data": d["data"], "total": d["total"], "linhas": [{"taxa": 23, "base": "77.90", "iva": "17.92"}],
                 "categoria_id": cat["id"], "conta": cat["conta"], "tratamento_iva": "dedutivel_50"}
        assert cliente.post(f"/api/faturas/{r['fatura_id']}/conferir", json={"dados": corpo}).status_code == 200
    return eid, [r["fatura_id"] for r in res], cat


def test_excel_bloqueia_e_desfaz(cliente, enviados, limpar, mensagens):
    eid, ids, cat = preparar(cliente, enviados, limpar)
    p = cliente.get("/api/exportacoes/previsao", params={"periodo": MES}).json()
    e = next(x for x in p["empresas"] if x["id"] == eid)
    assert e["prontas"] == 2 and e["exportadas"] == 0
    r = cliente.post("/api/exportacoes", json={"periodo": MES, "empresas": [eid], "formato": "xlsx"})
    assert r.status_code == 200, r.text
    lote = r.json()["lote"]
    f = cliente.get(f"/api/exportacoes/{lote}/ficheiro")
    assert f.status_code == 200
    wb = load_workbook(io.BytesIO(f.content))
    assert wb.sheetnames == ["Faturas", "Linhas de IVA", "Resumo do IVA"]
    fat = list(wb["Faturas"].iter_rows(values_only=True))
    assert len(fat) == 3 and fat[1][3] == "Papelaria Teste, Lda" and fat[1][9] == cat["conta"]
    assert float(fat[1][15]) == 8.96  # 50% de 17,92
    resumo = list(wb["Resumo do IVA"].iter_rows(values_only=True))
    assert float(resumo[1][5]) == 35.84 and float(resumo[1][6]) == 17.92
    # Exportadas: bloqueadas para edição e fora de uma nova exportação.
    assert cliente.post(f"/api/faturas/{ids[0]}/reabrir").status_code == 409
    assert cliente.post("/api/exportacoes", json={"periodo": MES, "empresas": [eid]}).json()["codigo"] == "nada_para_exportar"
    h = cliente.get("/api/exportacoes/previsao", params={"periodo": MES}).json()["historico"]
    assert h[0]["lote"] == lote and h[0]["faturas"] == 2
    # Desfazer devolve-as a "conferida".
    assert cliente.post(f"/api/exportacoes/{lote}/desfazer").json() == {"faturas": 2}
    assert cliente.get(f"/api/faturas/{ids[0]}").json()["estado"] == "conferida"
    assert cliente.post(f"/api/exportacoes/{lote}/desfazer").status_code == 409


def test_csv_e_zip(cliente, enviados, limpar, mensagens):
    eid, ids, _ = preparar(cliente, enviados, limpar)
    r = cliente.post("/api/exportacoes", json={"periodo": MES, "empresas": [eid], "formato": "csv", "marcar": False}).json()
    texto = cliente.get(f"/api/exportacoes/{r['lote']}/ficheiro").content.decode("utf-8-sig")
    linhas = list(csv.reader(io.StringIO(texto), delimiter=";"))
    assert linhas[0][0] == "Empresa" and linhas[1][16] == "95,82" and len(linhas) == 3
    # Sem marcar: continuam conferidas e podem ir num ZIP.
    r = cliente.post("/api/exportacoes", json={"periodo": MES, "empresas": [eid], "formato": "zip"}).json()
    z = zipfile.ZipFile(io.BytesIO(cliente.get(f"/api/exportacoes/{r['lote']}/ficheiro").content))
    nomes = z.namelist()
    assert any(n.endswith(".xlsx") for n in nomes) and sum(n.endswith(".pdf") for n in nomes) == 2
    assert all("/" in n for n in nomes if n.endswith(".pdf"))


def test_outro_gabinete_nao_descarrega(cliente, enviados, limpar, mensagens):
    eid, _, _ = preparar(cliente, enviados, limpar)
    lote = cliente.post("/api/exportacoes", json={"periodo": MES, "formato": "xlsx"}).json()["lote"]
    from fastapi.testclient import TestClient
    outro = TestClient(cliente.app)
    gabinete_confirmado(outro, enviados, limpar)
    assert outro.get(f"/api/exportacoes/{lote}/ficheiro").status_code == 404
    assert outro.post(f"/api/exportacoes/{lote}/desfazer").status_code == 404
