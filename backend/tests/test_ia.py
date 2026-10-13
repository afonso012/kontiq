"""Leitura de faturas sem QR: modo de teste (regras), modo Anthropic (simulado) e carregamento."""
import json
from datetime import date
from decimal import Decimal

import httpx

from app.core.config import get_settings
from app.faturas import ia
from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens  # noqa: F401
from tests.test_faturas import MES, carregar, criar_empresa


def pdf_com_texto(linhas: list[str]) -> bytes:
    """Um PDF mínimo com texto a sério (como os gerados pelos programas de faturação)."""
    def esc(t):
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("cp1252", "replace")
    stream = b"BT /F1 11 Tf 50 800 Td 14 TL " + b" ".join(b"(" + esc(l) + b") '" for l in linhas) + b" ET"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    out, pos = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        pos.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % p for p in pos)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


TEXTO_PT = """Talho Moderno do Sado, Lda
Rua Augusta 10, Setúbal · NIF 514873205
Fatura-recibo N.º FR 2026/88
Data: 05/10/2026
Cliente: NIF {nif}
Carne picada 2 kg   15,90
IVA 6%   0,95
Total a pagar   16,85 €"""


def test_regras_portugues_e_estrangeiro():
    x = ia._teste(TEXTO_PT.format(nif="512173850"), "512173850")
    assert (x.nif, x.tipo, x.numero, x.data, x.total) == ("514873205", "FR", "FR 2026/88", date(2026, 10, 5), Decimal("16.85"))
    assert x.fornecedor == "Talho Moderno do Sado, Lda" and x.linhas[0].iva == Decimal("0.95") and x.linhas[0].base == Decimal("15.90")
    assert Decimal("0.5") < x.confianca <= Decimal("0.85")
    estrangeira = ("Nimbus Cloud Services Ltd\nVAT number: IE3478221QH\nInvoice number: IE-2026-104882\n"
                   "Invoice date: 1 October 2026\nVAT 0% EUR 0.00\nTotal due EUR 1,024.59\nReverse charge")
    x = ia._teste(estrangeira, "516204874")
    assert (x.pais, x.nif, x.tipo, x.total, x.autoliquidacao) == ("IE", "IE3478221QH", "EST", Decimal("1024.59"), True)
    assert ia._teste("", "516204874") is None


def test_modo_anthropic_com_resposta_simulada(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "anthropic_api_key", "chave-de-teste")
    pedidos = []

    def responder(req: httpx.Request) -> httpx.Response:
        pedidos.append(json.loads(req.content))
        assert req.headers["x-api-key"] == "chave-de-teste"
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "registar_fatura", "input": {
            "fornecedor": "Café Central", "nif_fornecedor": "PT 514873205", "tipo": "FS", "numero": "FS 1/9",
            "data": "2026-10-03", "total": 12.3, "linhas_iva": [{"taxa": 23, "base": 10, "iva": 2.3}], "confianca": 0.93}}]})

    x = ia._anthropic(pdf_com_texto(["x"]), "application/pdf", "512173850",
                      cliente=httpx.Client(transport=httpx.MockTransport(responder)))
    assert pedidos[0]["tool_choice"]["name"] == "registar_fatura"
    assert pedidos[0]["messages"][0]["content"][0]["type"] == "document"
    assert (x.nif, x.pais, x.total, x.confianca, x.modo) == ("514873205", "PT", Decimal("12.30"), Decimal("0.93"), "anthropic")


def test_carregar_pdf_sem_qr_e_lido(cliente, enviados, limpar, mensagens):
    gabinete_confirmado(cliente, enviados, limpar)
    eid, nif = criar_empresa(cliente)
    hoje = date.today().replace(day=1).strftime("%d/%m/%Y")
    pdf = pdf_com_texto(TEXTO_PT.replace("05/10/2026", hoje).format(nif=nif).split("\n"))
    r = carregar(cliente, eid, ("talho.pdf", pdf))[0]
    assert r["estado"] == "ia" and r["metodo"] == "ia" and r["total"] == "16,85 €", r
    d = cliente.get(f"/api/faturas/{r['fatura_id']}").json()
    assert d["metodo"] == "ia" and d["fornecedor"]["nome"] == "Talho Moderno do Sado, Lda" and d["tipo_documento"] == "FR"
    assert 0.5 < d["confianca"] <= 0.85
    assert not [p for p in d["problemas"] if p["nivel"] == "erro"]
    lista = cliente.get(f"/api/empresas/{eid}/faturas", params={"periodo": MES}).json()
    assert lista["faturas"][0]["metodo"] == "ia"
