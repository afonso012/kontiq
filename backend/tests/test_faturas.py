"""Carregar documentos, ler o QR, conferir, rejeitar e duplicados — pela API."""
import io
from datetime import date

import pytest
import zxingcpp
from fastapi.testclient import TestClient
from PIL import Image

from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens  # noqa: F401

HOJE = date.today()
MES = HOJE.strftime("%Y-%m")
DATA = HOJE.replace(day=1).strftime("%Y%m%d")


def qr_texto(nif_empresa: str, numero="FT 2026/0457", nif_forn="514873205", total="95.82") -> str:
    return (f"A:{nif_forn}*B:{nif_empresa}*C:PT*D:FT*E:N*F:{DATA}*G:{numero}*H:JFR2M8KQ-457*"
            f"I1:PT*I7:77.90*I8:17.92*N:17.92*O:{total}*Q:aB3x*R:2153")


def imagem_com_qr(texto: str, formato: str) -> bytes:
    """Uma 'fatura' simples: folha branca com o QR no canto."""
    q = zxingcpp.create_barcode(texto, zxingcpp.BarcodeFormat.QRCode).to_image(scale=5)
    m = memoryview(q)
    qr = Image.frombytes("L", (m.shape[1], m.shape[0]), m.tobytes())
    folha = Image.new("RGB", (1240, 1754), "white")
    folha.paste(qr, (120, 1300))
    buf = io.BytesIO()
    folha.save(buf, formato)
    return buf.getvalue()


def criar_empresa(cliente) -> tuple[str, str]:
    nif = nif_aleatorio()
    r = cliente.post("/api/empresas", json={"nif": nif, "nome": "Empresa Faturas Teste"})
    assert r.status_code == 201, r.text
    return r.json()["id"], nif


def carregar(cliente, eid, *ficheiros):
    files = [("ficheiros", (nome, dados, "application/octet-stream")) for nome, dados in ficheiros]
    r = cliente.post(f"/api/empresas/{eid}/documentos", files=files, data={"periodo": MES})
    assert r.status_code == 200, r.text
    return r.json()["resultados"]


def test_carregar_pdf_e_foto_com_qr(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    eid, nif = criar_empresa(cliente)
    pdf = imagem_com_qr(qr_texto(nif), "PDF")
    res = carregar(cliente, eid,
                   ("fatura.pdf", pdf),
                   ("foto.jpg", imagem_com_qr(qr_texto(nif, "FT 2026/0999", total="95.82"), "JPEG")),
                   ("notas.txt", b"isto nao e uma fatura"),
                   ("branco.png", (lambda b: (Image.new("RGB", (400, 600), "white").save(b, "PNG"), b.getvalue())[1])(io.BytesIO())))
    estados = [r["estado"] for r in res]
    assert estados == ["lida", "lida", "erro", "manual"], res
    assert res[0]["metodo"] == "qr" and res[0]["numero"] == "FT 2026/0457" and res[0]["total"] == "95,82 €"

    # O mesmo ficheiro outra vez é reconhecido, não cria outra fatura.
    again = carregar(cliente, eid, ("fatura-copia.pdf", pdf))
    assert again[0]["estado"] == "repetido" and again[0]["fatura_id"] == res[0]["fatura_id"]

    lista = cliente.get(f"/api/empresas/{eid}/faturas", params={"periodo": MES}).json()
    assert lista["totais"]["faturas"] == 3 and lista["totais"]["por_conferir"] == 3

    d = cliente.get(f"/api/faturas/{res[0]['fatura_id']}").json()
    assert d["fornecedor"]["nif"] == "514873205" and d["total"] == "95.82" and d["metodo"] == "qr"
    assert d["linhas"][0]["tipo_taxa"] == "normal" and d["linhas"][0]["base"] == "77.90"
    assert d["fila"]["total"] == 3
    # O documento original abre, e só para o próprio gabinete.
    doc = cliente.get(f"/api/documentos/{d['documento']['id']}")
    assert doc.status_code == 200 and doc.content[:5] == b"%PDF-"
    pg = cliente.get(f"/api/documentos/{d['documento']['id']}/pagina/1")
    assert pg.status_code == 200 and pg.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert cliente.get(f"/api/documentos/{d['documento']['id']}/paginas").json() == {"paginas": 1}
    outro = TestClient(cliente.app)
    gabinete_confirmado(outro, enviados, limpar)
    assert outro.get(f"/api/documentos/{d['documento']['id']}").status_code == 404
    assert outro.get(f"/api/faturas/{d['id']}").status_code == 404


def test_conferir_com_regra_e_seguinte(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    eid, nif = criar_empresa(cliente)
    res = carregar(cliente, eid, ("a.pdf", imagem_com_qr(qr_texto(nif, "FT 1/1"), "PDF")),
                   ("b.pdf", imagem_com_qr(qr_texto(nif, "FT 1/2"), "PDF")))
    a, b = res[0]["fatura_id"], res[1]["fatura_id"]
    # Sem classificação não se pode conferir.
    r = cliente.post(f"/api/faturas/{a}/conferir", json={})
    assert r.status_code == 422 and r.json()["codigo"] == "sem_classificacao"
    op = cliente.get("/api/classificacao").json()
    cat = next(c for c in op["categorias"] if c["conta"])
    dados = cliente.get(f"/api/faturas/{a}").json()
    corpo = {"fornecedor": "Papelaria Teste, Lda", "nif": dados["fornecedor"]["nif"], "tipo_documento": "FT",
             "numero": dados["numero"], "data": dados["data"], "total": dados["total"],
             "linhas": [{"taxa": 23, "base": "77.90", "iva": "17.92"}],
             "categoria_id": cat["id"], "conta": cat["conta"], "tratamento_iva": "dedutivel"}
    r = cliente.post(f"/api/faturas/{a}/conferir", json={"lembrar": True, "dados": corpo})
    assert r.status_code == 200, r.text
    assert r.json()["fatura"]["estado"] == "conferida" and r.json()["seguinte"] == b
    # A regra aplica-se às faturas seguintes do mesmo fornecedor.
    nova = carregar(cliente, eid, ("c.pdf", imagem_com_qr(qr_texto(nif, "FT 1/3"), "PDF")))[0]["fatura_id"]
    d = cliente.get(f"/api/faturas/{nova}").json()
    assert d["conta"] == cat["conta"] and d["origem_classificacao"] == "regra" and d["fornecedor"]["nome"] == "Papelaria Teste, Lda"
    assert cliente.post(f"/api/faturas/{nova}/conferir", json={}).status_code == 200
    # Lote: a b não tem classificação? Tem (regra criada depois não muda a b), por isso falha com motivo.
    r = cliente.post("/api/faturas/conferir-lote", json={"ids": [b]}).json()
    assert r["conferidas"] == 0 and r["falhadas"][0]["id"] == b


def test_duplicado_e_rejeitar(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    eid, nif = criar_empresa(cliente)
    primeira = carregar(cliente, eid, ("orig.pdf", imagem_com_qr(qr_texto(nif, "FT 9/77"), "PDF")))[0]["fatura_id"]
    # Mesma fatura, ficheiro diferente (foto): é um duplicado.
    dup = carregar(cliente, eid, ("foto.jpg", imagem_com_qr(qr_texto(nif, "FT 9/77"), "JPEG")))[0]["fatura_id"]
    d = cliente.get(f"/api/faturas/{dup}").json()
    assert any(p["codigo"] == "duplicado" for p in d["problemas"]) and d["duplicado_de"] == primeira
    assert not any(p["codigo"] == "duplicado" for p in cliente.get(f"/api/faturas/{primeira}").json()["problemas"])
    painel = cliente.get("/api/painel", params={"periodo": MES}).json()
    assert any(a["codigo"] == "duplicado" and a["fatura_id"] == dup for a in painel["atencao"])
    # Com erro não se confere.
    assert cliente.post(f"/api/faturas/{dup}/conferir", json={}).json()["codigo"] == "tem_erros"
    r = cliente.post(f"/api/faturas/{dup}/rejeitar", json={"motivo": "Duplicado"})
    assert r.status_code == 200 and r.json()["estado"] == "rejeitada"
    lista = cliente.get(f"/api/empresas/{eid}/faturas", params={"periodo": MES}).json()
    assert lista["totais"]["faturas"] == 1  # a rejeitada não conta
    painel = cliente.get("/api/painel", params={"periodo": MES}).json()
    assert not any(a["codigo"] == "duplicado" for a in painel["atencao"])
    # Reabrir volta a detetar; "não é duplicado" resolve.
    d = cliente.post(f"/api/faturas/{dup}/reabrir").json()
    p = next(p for p in d["problemas"] if p["codigo"] == "duplicado")
    d = cliente.post(f"/api/faturas/{dup}/problemas/{p['id']}/resolver").json()
    assert not any(p["codigo"] == "duplicado" for p in d["problemas"])


def test_preencher_fatura_manual(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    eid, nif = criar_empresa(cliente)
    buf = io.BytesIO()
    Image.new("RGB", (500, 700), "white").save(buf, "JPEG")
    fid = carregar(cliente, eid, ("talao.jpg", buf.getvalue()))[0]["fatura_id"]
    d = cliente.get(f"/api/faturas/{fid}").json()
    assert d["metodo"] == "manual" and any(p["codigo"] == "sem_data" for p in d["problemas"])
    corpo = {"fornecedor": "Café Central", "nif": "123456780", "tipo_documento": "FS", "numero": "FS 1/2",
             "data": HOJE.isoformat(), "total": "12.30", "linhas": [{"taxa": 23, "base": "10.00", "iva": "2.30"}],
             "conta": "6251", "tratamento_iva": "nao_dedutivel"}
    d = cliente.put(f"/api/faturas/{fid}", json=corpo).json()
    assert any(p["codigo"] == "nif_invalido" for p in d["problemas"])
    corpo["nif"] = nif_aleatorio()
    corpo["total"] = "12.00"
    d = cliente.put(f"/api/faturas/{fid}", json=corpo).json()
    assert [p["codigo"] for p in d["problemas"] if p["nivel"] == "erro"] == ["contas_nao_batem"]
    corpo["total"] = "12.30"
    d = cliente.put(f"/api/faturas/{fid}", json=corpo).json()
    assert not [p for p in d["problemas"] if p["nivel"] == "erro"]
    assert cliente.post(f"/api/faturas/{fid}/conferir", json={}).status_code == 200
