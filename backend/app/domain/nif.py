"""Validação do Número de Identificação Fiscal português (NIF/NIPC)."""
import re

# Primeiros dígitos possíveis de um NIF/NIPC válido.
_PREFIXOS = ("1", "2", "3", "45", "5", "6", "70", "71", "72", "74", "75", "77", "79", "8", "90", "91", "98", "99")


def limpar(nif: str | None) -> str:
    """Remove espaços, pontos e o prefixo PT."""
    if not nif:
        return ""
    n = re.sub(r"[\s.\-]", "", str(nif)).upper()
    return n[2:] if n.startswith("PT") else n


def digito_controlo(oito_digitos: str) -> int:
    soma = sum(int(d) * (9 - i) for i, d in enumerate(oito_digitos))
    resto = 11 - soma % 11
    return 0 if resto >= 10 else resto


def nif_valido(nif: str | None) -> bool:
    """True se o NIF tem 9 dígitos, um prefixo possível e o dígito de controlo certo."""
    n = limpar(nif)
    if not re.fullmatch(r"\d{9}", n):
        return False
    if not n.startswith(_PREFIXOS):
        return False
    return digito_controlo(n[:8]) == int(n[8])
