"""Exportações (/api/exportacoes): pré-visualizar, gerar, descarregar, histórico, desfazer."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth.servico import ErroAuth
from ..core import armazenamento
from ..core.db import sessao_gabinete
from ..exportacoes import servico as svc
from .auth import SessaoAtual, exigir_gabinete
from .empresas import _mes

router = APIRouter(prefix="/api/exportacoes", tags=["Exportações"])


def _no_gabinete(atual: SessaoAtual, fn):
    with sessao_gabinete(atual.gabinete_id) as s:
        return fn(s)


@router.get("/previsao")
def previsao(periodo: str | None = Query(None), atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    mes = _mes(periodo)
    return _no_gabinete(atual, lambda s: {**svc.previsao(s, mes), "historico": svc.historico(s)})


class Pedido(BaseModel):
    periodo: str | None = None
    empresas: list[uuid.UUID] | None = Field(default=None, max_length=1000)
    formato: str = "xlsx"
    incluir_exportadas: bool = False
    marcar: bool = True


@router.post("")
def exportar(corpo: Pedido, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Gera o ficheiro. Com `marcar`, as faturas passam a 'exportada' e ficam bloqueadas."""
    mes = _mes(corpo.periodo)
    return _no_gabinete(atual, lambda s: svc.exportar(s, atual.gabinete_id, atual.utilizador_id, mes, corpo.empresas,
                                                       corpo.formato, corpo.incluir_exportadas, corpo.marcar))


@router.get("/{lote}/ficheiro")
def descarregar(lote: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)):
    chave, nome = _no_gabinete(atual, lambda s: svc.ficheiro(s, lote))
    caminho = armazenamento.caminho(chave)
    if not caminho.exists():
        raise ErroAuth(404, "ficheiro_em_falta", "O ficheiro desta exportação já não existe.")
    return FileResponse(caminho, filename=nome, headers={"Cache-Control": "private, no-store"})


@router.post("/{lote}/desfazer")
def desfazer(lote: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return {"faturas": _no_gabinete(atual, lambda s: svc.desfazer(s, atual.utilizador_id, lote))}
