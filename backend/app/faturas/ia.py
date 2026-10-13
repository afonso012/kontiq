"""Leitura de faturas sem código QR.

Dois modos (variável IA_MODO):

- "teste" (por omissão): sem custos e sem internet. Lê o TEXTO do PDF com regras
  simples (NIF, número, data, totais, IVA). Funciona com PDFs gerados por
  programas; fotografias e digitalizações ficam para preencher à mão. Serve para
  testar o fluxo completo antes de haver uma chave.
- "anthropic": envia o documento ao Claude (API da Anthropic) e recebe os campos
  estruturados. Precisa de ANTHROPIC_API_KEY. Cada fatura lida tem custo.
- "desligada": nada; as faturas sem QR entram para preencher.

Em qualquer modo o resultado é uma `Extracao` com uma confiança de 0 a 1.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from ..core.config import get_settings
from ..domain.nif import nif_valido

log = logging.getLogger("faturas.ia")

PAISES_UE = {"AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES", "FI", "FR", "HR", "HU", "IE", "IT", "LT",
             "LU", "LV", "MT", "NL", "PL", "PT", "RO", "SE", "SI", "SK", "XI"}
TIPOS = ("FT", "FS", "FR", "NC", "ND", "VD", "EST", "OUTRO")


@dataclass
class LinhaExtraida:
    taxa: Decimal | None
    base: Decimal
    iva: Decimal


@dataclass
class Extracao:
    fornecedor: str | None = None
    nif: str | None = None
    pais: str = "PT"
    tipo: str = "FT"
    numero: str | None = None
    data: date | None = None
    total: Decimal | None = None
    linhas: list[LinhaExtraida] = field(default_factory=list)
    autoliquidacao: bool = False
    confianca: Decimal = Decimal("0")
    modo: str = "teste"

    @property
    def util(self) -> bool:
        return bool(self.total or self.nif or self.numero)


def extrair(dados: bytes, mime: str, texto: str, nif_empresa: str) -> Extracao | None:
    modo = get_settings().ia_modo
    if modo == "desligada":
        return None
    try:
        if modo == "anthropic":
            return _anthropic(dados, mime, nif_empresa)
        return _teste(texto, nif_empresa)
    except Exception as e:  # nunca deixar a leitura bloquear o carregamento
        log.warning("Leitura (%s) falhou: %s", modo, e)
        return None


# ---------------------------------------------------------------- modo de teste (regras sobre o texto)

_MESES = {m: i + 1 for i, m in enumerate(
    ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"])}
_MESES.update({m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])})
_VALOR = r"(?<![\d.,])(\d{1,3}(?:,\d{3})+\.\d{2}|\d{1,3}(?:[ .\u00a0]\d{3})+,\d{2}|\d+[.,]\d{2})(?!\d)"


def _dec(txt: str) -> Decimal | None:
    t = txt.replace(" ", " ").strip()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})*\.\d{2}", t):     # 1,234.56 (inglês)
        t = t.replace(",", "")
    else:                                                 # 1 234,56 / 1.234,56 (português)
        t = t.replace(" ", "").replace(".", "").replace(",", ".") if "," in t else t.replace(" ", "")
    try:
        return Decimal(t).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _data(texto: str) -> date | None:
    for rotulo in (r"(?:data(?: de emiss[aã]o)?|invoice date|date)\s*[:.]?\s*", ""):
        for m in re.finditer(rotulo + r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", texto, re.I):
            try:
                return date(int(m[3]), int(m[2]), int(m[1]))
            except ValueError:
                pass
        for m in re.finditer(rotulo + r"(\d{4})-(\d{2})-(\d{2})", texto, re.I):
            try:
                return date(int(m[1]), int(m[2]), int(m[3]))
            except ValueError:
                pass
        for m in re.finditer(rotulo + r"(\d{1,2})\s+(?:de\s+)?([A-Za-zçÇ]{3})[a-zç]*\.?\s+(?:de\s+)?(\d{4})", texto, re.I):
            mes = _MESES.get(m[2].lower()[:3])
            if mes:
                try:
                    return date(int(m[3]), mes, int(m[1]))
                except ValueError:
                    pass
    return None


def _teste(texto: str, nif_empresa: str) -> Extracao | None:
    if not texto or len(texto.strip()) < 30:
        return None  # sem texto (fotografia, digitalização): fica para preencher
    t = texto.replace("\r", "")
    linhas = [l.strip() for l in t.split("\n") if l.strip()]
    x = Extracao(modo="teste")

    # NIF português do fornecedor: o primeiro válido que não é o da empresa nem consumidor final.
    for m in re.finditer(r"(?<!\d)(\d{9})(?!\d)", t.replace(" ", "")):
        if nif_valido(m[1]) and m[1] not in (nif_empresa, "999999990"):
            x.nif = m[1]
            break
    if not x.nif:  # fornecedor estrangeiro: número de IVA da UE
        for m in re.finditer(r"\b([A-Z]{2})\s?([0-9A-Z]{8,12})\b", t):
            if m[1] in PAISES_UE and m[1] != "PT":
                x.pais, x.nif = ("GR" if m[1] == "EL" else m[1]), m[1] + m[2]
                break

    if x.nif and x.pais == "PT":
        from .leitura import nome_provavel_fornecedor
        x.fornecedor = nome_provavel_fornecedor(t, x.nif)
    x.fornecedor = x.fornecedor or (linhas[0][:120] if linhas else None)

    m = re.search(r"(?:invoice (?:number|no\.?|#)|n\.?\s?[ºo°]\s*(?:da fatura)?|fatura(?:-recibo)?\s+n\.?[ºo°]?)\s*[:#]?\s*([A-Z0-9][A-Z0-9 /\-.]{2,30}[0-9])", t, re.I)
    if m:
        x.numero = re.sub(r"\s+", " ", m[1]).strip()
    x.data = _data(t)

    baixo = t.lower()
    if re.search(r"fatura[- ]recibo", baixo):
        x.tipo = "FR"
    elif re.search(r"fatura simplificada", baixo):
        x.tipo = "FS"
    elif re.search(r"nota de cr[eé]dito|credit note", baixo):
        x.tipo = "NC"
    elif x.pais != "PT":
        x.tipo = "EST"
    x.autoliquidacao = bool(re.search(r"reverse charge|autoliquida|art(?:igo|\.)?\s*196", baixo))

    # Total: o maior valor numa linha que fala de total (a pagar / due / total).
    totais = []
    for l in linhas:
        if re.search(r"total|a pagar|amount due|balance due", l, re.I) and not re.search(r"sub-?total|il[ií]quido|base", l, re.I):
            totais += [v for v in (_dec(v) for v in re.findall(_VALOR, l)) if v is not None]
    if totais:
        x.total = max(totais)

    # IVA: linhas com "IVA"/"VAT" e uma percentagem.
    for l in linhas:
        m = re.search(r"(?:iva|vat)\D{0,15}?(\d{1,2}(?:[.,]\d{1,2})?)\s*%", l, re.I)
        if not m:
            continue
        taxa = _dec(m[1].replace(".", ",") + ("" if "," in m[1] or "." in m[1] else ",00"))
        valores = [v for v in (_dec(v) for v in re.findall(_VALOR, l[m.end():])) if v is not None]
        if taxa is not None and valores:
            x.linhas.append(LinhaExtraida(taxa=taxa, base=Decimal("0"), iva=valores[-1]))
    if x.total is not None:
        if len(x.linhas) == 1:
            l = x.linhas[0]
            l.base = (x.total - l.iva).quantize(Decimal("0.01"))
        elif not x.linhas:
            x.linhas.append(LinhaExtraida(taxa=None, base=x.total, iva=Decimal("0")))
        else:  # várias taxas: base de cada uma a partir do IVA
            for l in x.linhas:
                if l.taxa:
                    l.base = (l.iva * 100 / l.taxa).quantize(Decimal("0.01"))

    encontrados = sum(bool(v) for v in (x.nif, x.numero, x.data, x.total, x.fornecedor))
    soma_ok = x.total is not None and abs(sum((l.base + l.iva for l in x.linhas), Decimal("0")) - x.total) <= Decimal("0.02")
    # Teto de 0,85: é uma leitura por regras, convém sempre olhar.
    x.confianca = min(Decimal("0.85"), (Decimal(encontrados) / 5 * Decimal("0.8") + (Decimal("0.1") if soma_ok else 0))).quantize(Decimal("0.01"))
    return x if x.util else None


# ---------------------------------------------------------------- modo Anthropic (Claude)

_PROMPT = """És um assistente de contabilidade português. Lê esta fatura de COMPRA da empresa com NIF {nif}.
Devolve os dados com a ferramenta registar_fatura. Regras:
- fornecedor = quem EMITE a fatura (não a empresa {nif}).
- nif_fornecedor: NIF português de 9 dígitos, ou o número de IVA com o prefixo do país (ex.: IE3478221QH).
- data no formato AAAA-MM-DD; valores com ponto decimal; uma linha de IVA por taxa.
- Se for nota de crédito, tipo = NC. Fatura estrangeira = EST.
- Se um campo não estiver legível, omite-o. Não inventes.
- confianca: 0 a 1, a tua certeza global na leitura."""

_FERRAMENTA = {
    "name": "registar_fatura",
    "description": "Regista os dados lidos da fatura.",
    "input_schema": {
        "type": "object",
        "properties": {
            "fornecedor": {"type": "string"}, "nif_fornecedor": {"type": "string"},
            "pais_fornecedor": {"type": "string", "description": "Código ISO de 2 letras"},
            "tipo": {"type": "string", "enum": list(TIPOS)}, "numero": {"type": "string"},
            "data": {"type": "string"}, "total": {"type": "number"}, "moeda": {"type": "string"},
            "linhas_iva": {"type": "array", "items": {"type": "object", "properties": {
                "taxa": {"type": "number"}, "base": {"type": "number"}, "iva": {"type": "number"}},
                "required": ["base", "iva"]}},
            "autoliquidacao": {"type": "boolean"}, "confianca": {"type": "number"},
        },
        "required": ["confianca"],
    },
}


def _bloco(dados: bytes, mime: str) -> dict:
    if mime == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                               "data": base64.b64encode(dados).decode()}}
    from PIL import Image, ImageOps
    if mime == "image/heic":
        import pillow_heif
        pillow_heif.register_heif_opener()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(dados))).convert("RGB")
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}


def _anthropic(dados: bytes, mime: str, nif_empresa: str, cliente=None) -> Extracao | None:
    import httpx
    s = get_settings()
    if not s.anthropic_api_key:
        log.warning("IA_MODO=anthropic mas falta ANTHROPIC_API_KEY.")
        return None
    corpo = {
        "model": s.ia_modelo, "max_tokens": 1024,
        "tools": [_FERRAMENTA], "tool_choice": {"type": "tool", "name": "registar_fatura"},
        "messages": [{"role": "user", "content": [_bloco(dados, mime), {"type": "text", "text": _PROMPT.format(nif=nif_empresa)}]}],
    }
    http = cliente or httpx.Client(timeout=60)
    r = http.post("https://api.anthropic.com/v1/messages", json=corpo,
                  headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"})
    r.raise_for_status()
    uso = next((b["input"] for b in r.json().get("content", []) if b.get("type") == "tool_use"), None)
    return _de_json(uso) if uso else None


def _de_json(d: dict) -> Extracao | None:
    def dec(v):
        try:
            return Decimal(str(v)).quantize(Decimal("0.01")) if v is not None else None
        except InvalidOperation:
            return None
    x = Extracao(modo="anthropic")
    x.fornecedor = (d.get("fornecedor") or "")[:200] or None
    nif = re.sub(r"[\s.\-]", "", d.get("nif_fornecedor") or "").upper()
    pais = (d.get("pais_fornecedor") or "").upper()[:2]
    if re.fullmatch(r"PT\d{9}", nif):
        nif = nif[2:]
    x.pais = pais or ("PT" if re.fullmatch(r"\d{9}", nif) else nif[:2] if nif[:2].isalpha() else "PT")
    x.nif = nif or None
    x.tipo = d.get("tipo") if d.get("tipo") in TIPOS else ("FT" if x.pais == "PT" else "EST")
    x.numero = (d.get("numero") or "")[:80] or None
    try:
        x.data = date.fromisoformat(d["data"]) if d.get("data") else None
    except ValueError:
        x.data = None
    x.total = dec(d.get("total"))
    x.linhas = [LinhaExtraida(dec(l.get("taxa")), dec(l.get("base")) or Decimal("0"), dec(l.get("iva")) or Decimal("0"))
                for l in d.get("linhas_iva") or [] if isinstance(l, dict)]
    x.autoliquidacao = bool(d.get("autoliquidacao"))
    try:
        x.confianca = max(Decimal("0"), min(Decimal("1"), Decimal(str(d.get("confianca", 0))))).quantize(Decimal("0.01"))
    except InvalidOperation:
        x.confianca = Decimal("0.5")
    return x if x.util else None
