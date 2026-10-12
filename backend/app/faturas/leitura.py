"""Ler um documento carregado: detetar o tipo, encontrar o código QR da AT e o texto.

- PDF: cada página (até 3) é desenhada a 200 ppp e procura-se o QR; o texto vem do PDF.
- Fotografia (JPG, PNG, WEBP, HEIC): procura-se o QR na imagem, também em tons de
  cinzento e reduzida, porque as fotos de telemóvel são grandes e às vezes tremidas.
"""
from __future__ import annotations

import io
import logging
from dataclasses import dataclass

log = logging.getLogger("faturas.leitura")

TIPOS = {
    "application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic",
}


def tipo_por_conteudo(dados: bytes) -> str | None:
    """Tipo MIME a partir dos primeiros bytes (não confiamos na extensão nem no browser)."""
    if dados[:5] == b"%PDF-":
        return "application/pdf"
    if dados[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    if dados[4:8] == b"ftyp" and dados[8:12] in (b"heic", b"heix", b"mif1", b"msf1", b"hevc", b"heim", b"heis"):
        return "image/heic"
    return None


@dataclass
class Leitura:
    qr: str | None
    texto: str
    paginas: int
    erro: str | None = None


def _qr_em(imagem) -> str | None:
    import zxingcpp
    from PIL import ImageOps

    tentativas = [imagem, ImageOps.grayscale(imagem)]
    if max(imagem.size) > 2400:
        reduzida = imagem.copy()
        reduzida.thumbnail((2000, 2000))
        tentativas.append(ImageOps.grayscale(reduzida))
    for img in tentativas:
        for r in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode):
            # O QR da AT começa sempre por "A:" (NIF do emitente).
            if r.text.startswith("A:") and "*" in r.text:
                return r.text
    return None


def ler(dados: bytes, mime: str) -> Leitura:
    try:
        if mime == "application/pdf":
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(dados)
            texto, qr = [], None
            for i in range(min(len(pdf), 3)):
                pagina = pdf[i]
                texto.append(pagina.get_textpage().get_text_range())
                if not qr:
                    qr = _qr_em(pagina.render(scale=200 / 72).to_pil())
            return Leitura(qr, "\n".join(texto), len(pdf))
        from PIL import Image, ImageOps
        if mime == "image/heic":
            import pillow_heif
            pillow_heif.register_heif_opener()
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(dados)))
        img.load()
        return Leitura(_qr_em(img.convert("RGB")), "", 1)
    except Exception as e:  # ficheiro estragado ou formato inesperado
        log.warning("Não consegui ler o documento: %s", e)
        return Leitura(None, "", 0, "Não conseguimos abrir este ficheiro. Está estragado ou protegido?")


def nome_provavel_fornecedor(texto: str, nif: str) -> str | None:
    """Palpite do nome do fornecedor a partir do texto do PDF: a linha antes do NIF
    ou a primeira linha com cara de nome de empresa."""
    linhas = [l.strip() for l in texto.splitlines() if l.strip()]
    sufixos = (", sa", " sa", ", lda", " lda", " unipessoal", ", s.a.", " s.a.", ", lda.", " lda.")
    for l in linhas[:15]:
        if any(l.lower().endswith(x) for x in sufixos) and len(l) <= 120:
            return l
    for i, l in enumerate(linhas):
        if nif in l.replace(" ", "") and i > 0 and len(linhas[i - 1]) <= 120:
            return linhas[i - 1]
    return None
