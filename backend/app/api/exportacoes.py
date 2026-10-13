"""Exportações (/api/exportacoes): pré-visualizar, gerar, descarregar, histórico, desfazer."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..auth.servico import ErroAuth
from ..core import armazenamento
from ..core.db import sessao_gabinete
from ..exportacoes import modelos as mod
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
    modelo: uuid.UUID | None = None


@router.post("")
def exportar(corpo: Pedido, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Gera o ficheiro. Com `marcar`, as faturas passam a 'exportada' e ficam bloqueadas."""
    mes = _mes(corpo.periodo)
    return _no_gabinete(atual, lambda s: svc.exportar(s, atual.gabinete_id, atual.utilizador_id, mes, corpo.empresas,
                                                       corpo.formato, corpo.incluir_exportadas, corpo.marcar, corpo.modelo))


# ---------------------------------------------------------------- configuração e modelos dos programas

@router.get("/configuracao")
def ver_config(atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: {**mod.ver_config(s, atual.gabinete_id), "modelos": mod.listar(s)})


@router.put("/configuracao")
def gravar_config(corpo: dict, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: mod.gravar_config(s, atual.gabinete_id, atual.utilizador_id, corpo))


@router.post("/modelos", status_code=201)
async def carregar_modelo(ficheiro: UploadFile = File(...), programa: str = Form(...), nome: str | None = Form(None),
                          atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Recebe o modelo de importação (Excel) do programa e sugere que dados vão em cada coluna."""
    dados = await ficheiro.read(mod.MAX_MODELO + 1)
    return _no_gabinete(atual, lambda s: mod.carregar(s, atual.gabinete_id, atual.utilizador_id, ficheiro.filename or "modelo.xlsx",
                                                      dados, programa, nome))


class Mapeamento(BaseModel):
    nome: str | None = Field(default=None, max_length=80)
    programa: str | None = None
    mapeamento: dict[str, str]


@router.put("/modelos/{modelo_id}")
def mapear_modelo(modelo_id: uuid.UUID, corpo: Mapeamento, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: mod.atualizar(s, atual.gabinete_id, atual.utilizador_id, modelo_id, corpo.nome,
                                                       corpo.programa, corpo.mapeamento))


@router.delete("/modelos/{modelo_id}")
def apagar_modelo(modelo_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    _no_gabinete(atual, lambda s: mod.apagar(s, atual.gabinete_id, atual.utilizador_id, modelo_id))
    return {"ok": True}


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
