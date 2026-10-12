"""Leitura do código QR das faturas portuguesas (especificação técnica da AT).

O texto do QR é uma lista de campos `CÓDIGO:valor` separados por `*`, por ex.:
    A:514873205*B:999999990*C:PT*D:FT*E:N*F:20261009*G:FT 2026/0457*H:JFR2M8KQ-457*
    I1:PT*I7:77.90*I8:17.92*N:17.92*O:95.82*Q:aB3x*R:2153

Campos principais:
    A  NIF do emitente (o fornecedor)      B  NIF do adquirente
    C  País do ADQUIRENTE                  D  Tipo de documento (FT, FS, FR, NC...)
    E  Estado do documento                 F  Data (AAAAMMDD)
    G  Identificação única do documento    H  ATCUD
    I/J/K  Resumo do IVA no continente / Açores / Madeira:
        x1 espaço fiscal, x2 base isenta, x3 base taxa reduzida, x4 IVA reduzida,
        x5 base taxa intermédia, x6 IVA intermédia, x7 base taxa normal, x8 IVA normal
    L  Não sujeito / não tributável         M  Imposto do selo
    N  Total de impostos                    O  Total do documento com impostos
    P  Retenção na fonte                    Q  4 caracteres do hash
    R  Nº do certificado do programa        S  Outras informações
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

_ESPACOS = {"I": "PT", "J": "PT-AC", "K": "PT-MA"}
_TAXAS = (("3", "4", "reduzida"), ("5", "6", "intermedia"), ("7", "8", "normal"))


@dataclass
class LinhaIVAQR:
    espaco_fiscal: str
    tipo_taxa: str
    base: Decimal
    iva: Decimal

    @property
    def taxa(self) -> Decimal | None:
        if self.base == 0:
            return None
        return (self.iva / self.base * 100).quantize(Decimal("0.01"))


@dataclass
class FaturaQR:
    nif_emitente: str
    nif_adquirente: str | None
    pais_adquirente: str | None
    tipo_documento: str
    estado: str | None
    data_emissao: date | None
    numero: str | None
    atcud: str | None
    linhas_iva: list[LinhaIVAQR] = field(default_factory=list)
    nao_sujeito: Decimal = Decimal("0")
    imposto_selo: Decimal = Decimal("0")
    total_impostos: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    retencao: Decimal = Decimal("0")
    certificado: str | None = None
    texto_original: str = ""

    @property
    def base_total(self) -> Decimal:
        return sum((l.base for l in self.linhas_iva), Decimal("0")) + self.nao_sujeito

    @property
    def iva_total(self) -> Decimal:
        return sum((l.iva for l in self.linhas_iva), Decimal("0"))


class QRInvalido(ValueError):
    pass


def _dec(v: str | None) -> Decimal:
    if not v:
        return Decimal("0")
    try:
        return Decimal(v.replace(",", "."))
    except InvalidOperation as e:
        raise QRInvalido(f"Valor numérico inválido: {v!r}") from e


def _data(v: str | None) -> date | None:
    if not v or len(v) != 8 or not v.isdigit():
        return None
    return date(int(v[:4]), int(v[4:6]), int(v[6:8]))


def ler_qr(texto: str) -> FaturaQR:
    """Converte o texto de um QR da AT em dados estruturados. Lança QRInvalido."""
    if not texto or not texto.startswith("A:") or "*" not in texto:
        raise QRInvalido("Não é um código QR de fatura portuguesa.")
    campos: dict[str, str] = {}
    for parte in texto.split("*"):
        cod, sep, valor = parte.partition(":")
        if sep:
            campos[cod.strip()] = valor.strip()
    for obrigatorio in ("A", "D", "O"):
        if obrigatorio not in campos:
            raise QRInvalido(f"Falta o campo {obrigatorio} no código QR.")

    linhas: list[LinhaIVAQR] = []
    for letra, espaco in _ESPACOS.items():
        if f"{letra}1" not in campos:
            continue
        isenta = _dec(campos.get(f"{letra}2"))
        if isenta:
            linhas.append(LinhaIVAQR(espaco, "isenta", isenta, Decimal("0")))
        for b, i, tipo in _TAXAS:
            base, iva = _dec(campos.get(f"{letra}{b}")), _dec(campos.get(f"{letra}{i}"))
            if base or iva:
                linhas.append(LinhaIVAQR(espaco, tipo, base, iva))

    return FaturaQR(
        nif_emitente=campos["A"],
        nif_adquirente=campos.get("B"),
        pais_adquirente=campos.get("C"),
        tipo_documento=campos["D"],
        estado=campos.get("E"),
        data_emissao=_data(campos.get("F")),
        numero=campos.get("G"),
        atcud=campos.get("H"),
        linhas_iva=linhas,
        nao_sujeito=_dec(campos.get("L")),
        imposto_selo=_dec(campos.get("M")),
        total_impostos=_dec(campos.get("N")),
        total=_dec(campos.get("O")),
        retencao=_dec(campos.get("P")),
        certificado=campos.get("R"),
        texto_original=texto,
    )
