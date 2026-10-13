"""Formatos de importação: lançamentos genéricos, TOConline e modelos carregados pelo gabinete."""
import io
import zipfile

from openpyxl import Workbook, load_workbook

from app.exportacoes import lancamentos as L
from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens  # noqa: F401
from tests.test_exportacoes import preparar
from tests.test_faturas import MES, carregar, criar_empresa, imagem_com_qr, qr_texto


def _ficheiro(cliente, corpo):
    r = cliente.post("/api/exportacoes", json={"periodo": MES, "marcar": False, **corpo})
    assert r.status_code == 200, r.text
    return r.json(), cliente.get(f"/api/exportacoes/{r.json()['lote']}/ficheiro").content


def test_lancamentos_genericos_equilibrados(cliente, enviados, limpar, mensagens):
    eid, ids, cat = preparar(cliente, enviados, limpar)
    info, conteudo = _ficheiro(cliente, {"empresas": [eid], "formato": "lancamentos"})
    assert info["nome"].startswith("Lançamentos ") and info["nome"].endswith(".xlsx")
    linhas = list(load_workbook(io.BytesIO(conteudo)).worksheets[0].iter_rows(values_only=True))
    cab, movs = linhas[0], linhas[1:]
    assert cab[:4] == ("Lançamento", "Diário", "Tipo doc.", "Data") and len(movs) == 6  # 2 faturas × 3 movimentos
    primeira = [m for m in movs if m[0] == 1]
    assert [(m[7], m[8], m[9]) for m in primeira] == [(cat["conta"], 86.86, None), ("2432", 8.96, None), ("2211", None, 95.82)]
    assert round(sum(m[8] or 0 for m in movs), 2) == round(sum(m[9] or 0 for m in movs), 2) == 191.64
    assert primeira[0][1] == "2" and primeira[0][2] == "FT" and primeira[2][10]  # diário, tipo e NIF do fornecedor


def test_configuracao_e_toconline(cliente, enviados, limpar, mensagens):
    eid, ids, cat = preparar(cliente, enviados, limpar)
    c = cliente.get("/api/exportacoes/configuracao").json()
    assert c["config"]["conta_fornecedor"] == "2211" and c["modelos"] == []
    assert cliente.put("/api/exportacoes/configuracao", json={"conta_fornecedor": "22a"}).status_code == 422
    novo = cliente.put("/api/exportacoes/configuracao", json={
        "diario": "COMPRAS", "conta_fornecedor": "2211", "fornecedor_com_nif": True,
        "contas_iva": {"normal": "243123"}, "tipos_documento": {"FT": "FTC"}}).json()["config"]
    assert novo["contas_iva"] == {"normal": "243123", "intermedia": "2432", "reduzida": "2432"} and novo["tipos_documento"]["FT"] == "FTC"

    info, conteudo = _ficheiro(cliente, {"empresas": [eid], "formato": "toconline"})
    assert info["nome"].startswith("TOConline ") and info["nome"].endswith(".xlsx")
    linhas = list(load_workbook(io.BytesIO(conteudo)).active.iter_rows(values_only=True))
    assert list(linhas[0]) == L.CAB_TOCONLINE
    gasto, iva, forn = linhas[1:4]
    assert gasto[1] == "COMPRAS" and gasto[2] == "FTC" and gasto[7] == "Nenhum" and gasto[12] == 86.86
    assert iva[10] == "243123" and iva[12] == 8.96
    assert forn[7] == "Fornecedor" and forn[10] == "2211" + forn[8] and forn[13] == 95.82


def _modelo_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Importar"
    ws.append(["Modelo de importação de movimentos"])
    ws.append(["Data", "Diário", "Nº Documento", "Conta", "Descrição", "Débito", "Crédito", "NIF", "Código IVA"])
    ws.append(["01/01/2026", "1", "EXEMPLO", "6222", "Linha de exemplo", 10, None, "500000000", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_modelo_do_programa(cliente, enviados, limpar, mensagens):
    eid, ids, cat = preparar(cliente, enviados, limpar)
    # Segunda empresa com uma fatura conferida: o modelo sai um ficheiro por empresa, num ZIP.
    e2, nif2 = criar_empresa(cliente)
    r = carregar(cliente, e2, ("c.pdf", imagem_com_qr(qr_texto(nif2, "FT 7/7"), "PDF")))[0]
    d = cliente.get(f"/api/faturas/{r['fatura_id']}").json()
    assert cliente.post(f"/api/faturas/{r['fatura_id']}/conferir", json={"dados": {
        "fornecedor": "Papelaria", "nif": d["fornecedor"]["nif"], "tipo_documento": "FT", "numero": d["numero"], "data": d["data"],
        "total": d["total"], "linhas": [{"taxa": 23, "base": "77.90", "iva": "17.92"}], "categoria_id": cat["id"],
        "conta": cat["conta"], "tratamento_iva": "dedutivel"}}).status_code == 200

    assert cliente.post("/api/exportacoes/modelos", data={"programa": "sage"},
                        files={"ficheiro": ("x.xls", b"\xd0\xcf\x11\xe0velho", "application/vnd.ms-excel")}).status_code == 422
    m = cliente.post("/api/exportacoes/modelos", data={"programa": "sage"},
                     files={"ficheiro": ("Modelo Sage.xlsx", _modelo_xlsx(), "application/octet-stream")})
    assert m.status_code == 201, m.text
    m = m.json()
    assert m["folha"] == "Importar" and m["linha_cabecalho"] == 2 and len(m["cabecalhos"]) == 9
    assert m["sugestao"] == {"1": "data_lancamento", "2": "diario", "3": "referencia", "4": "conta", "5": "descricao",
                             "6": "debito", "7": "credito", "8": "nif_terceiro", "9": "codigo_iva"}
    # Por mapear não exporta; sem conta ou valores o mapeamento é recusado.
    assert cliente.post("/api/exportacoes", json={"periodo": MES, "formato": "modelo", "modelo": m["id"], "marcar": False}).json()["codigo"] == "modelo_por_mapear"
    assert cliente.put(f"/api/exportacoes/modelos/{m['id']}", json={"mapeamento": {"1": "data_lancamento"}}).json()["codigo"] == "falta_conta"
    ok = cliente.put(f"/api/exportacoes/modelos/{m['id']}", json={"mapeamento": m["sugestao"], "nome": "Sage 50"})
    assert ok.status_code == 200 and ok.json()["nome"] == "Sage 50"
    assert cliente.get("/api/exportacoes/previsao", params={"periodo": MES}).json()["modelos"][0]["pronto"] is True

    info, conteudo = _ficheiro(cliente, {"empresas": [eid, e2], "formato": "modelo", "modelo": m["id"]})
    assert info["nome"].endswith(".zip")
    z = zipfile.ZipFile(io.BytesIO(conteudo))
    assert len(z.namelist()) == 2 and all(n.startswith("Sage 50 ") for n in z.namelist())
    for nome in z.namelist():
        ws = load_workbook(io.BytesIO(z.read(nome)))["Importar"]
        linhas = list(ws.iter_rows(values_only=True))
        assert linhas[0][0] == "Modelo de importação de movimentos" and linhas[1][0] == "Data"
        assert "EXEMPLO" not in [l[2] for l in linhas[2:]]  # a linha de exemplo saiu
        movs = linhas[2:]
        assert round(sum(l[5] or 0 for l in movs), 2) == round(sum(l[6] or 0 for l in movs), 2)
        assert all(l[3] for l in movs) and movs[0][1] == "2"

    assert cliente.delete(f"/api/exportacoes/modelos/{m['id']}").status_code == 200
    assert cliente.get("/api/exportacoes/configuracao").json()["modelos"] == []


def test_sugestoes_de_colunas():
    cab = [{"col": i, "nome": n} for i, n in enumerate(
        ["Número de ordem do lançamento", "Data de documento", "Tipo de Documento", "Código da conta a movimentar",
         "Valor", "Natureza", "Nome do terceiro", "Base tributável", "Taxa"], 1)]
    assert L.sugerir(cab) == {"1": "n", "2": "data_documento", "3": "tipo_documento", "4": "conta", "5": "valor",
                              "6": "natureza", "7": "nome_terceiro", "8": "base_iva", "9": "taxa_iva"}
