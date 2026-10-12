"""Guardar e ler os ficheiros originais (PDFs e fotografias das faturas).

Em desenvolvimento ficam numa pasta do disco (dados/documentos). A chave é
`<gabinete>/<empresa>/<sha256>.<ext>`: nunca vem do nome que o utilizador deu
ao ficheiro, por isso não há como escrever fora da pasta.
"""
from __future__ import annotations

from pathlib import Path

from .config import get_settings


def _raiz() -> Path:
    s = get_settings()
    if s.armazenamento != "local":
        raise NotImplementedError("Só o armazenamento local está configurado nesta fase.")
    return Path(s.pasta_documentos)


def _caminho(chave: str) -> Path:
    raiz = _raiz().resolve()
    p = (raiz / chave).resolve()
    if raiz not in p.parents:
        raise ValueError("Chave de armazenamento inválida.")
    return p


def guardar(chave: str, dados: bytes) -> None:
    p = _caminho(chave)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(dados)
    tmp.replace(p)


def caminho(chave: str) -> Path:
    return _caminho(chave)
