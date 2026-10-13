"""Equipa do gabinete (/api/equipa) e aceitação de convites (/api/convites, sem sessão)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..core.db import sessao_gabinete
from ..equipa import servico as svc
from .auth import SessaoAtual, contexto, executar, exigir_gabinete, por_cookie, trocar_sessao

router = APIRouter(tags=["Equipa"])


class NovoConvite(BaseModel):
    email: str = Field(max_length=254)
    papel: str = "colaborador"


class Papel(BaseModel):
    papel: str


class Aceitar(BaseModel):
    nome: str | None = Field(default=None, max_length=200)
    password: str = Field(max_length=200)


def _no_gabinete(atual: SessaoAtual, fn):
    with sessao_gabinete(atual.gabinete_id) as s:
        return fn(s)


@router.get("/api/equipa")
def listar(atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: svc.listar(s, atual.gabinete_id, atual.utilizador_id))


@router.post("/api/equipa/convites", status_code=201)
def convidar(corpo: NovoConvite, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: svc.convidar(s, atual.gabinete_id, atual.utilizador_id, corpo.email, corpo.papel))


@router.post("/api/equipa/convites/{convite_id}/reenviar")
def reenviar(convite_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    _no_gabinete(atual, lambda s: svc.reenviar(s, atual.gabinete_id, atual.utilizador_id, convite_id))
    return {"ok": True}


@router.delete("/api/equipa/convites/{convite_id}")
def cancelar(convite_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    _no_gabinete(atual, lambda s: svc.cancelar(s, atual.gabinete_id, atual.utilizador_id, convite_id))
    return {"ok": True}


@router.put("/api/equipa/membros/{membro_id}")
def mudar_papel(membro_id: uuid.UUID, corpo: Papel, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    _no_gabinete(atual, lambda s: svc.mudar_papel(s, atual.gabinete_id, atual.utilizador_id, membro_id, corpo.papel))
    return {"ok": True}


@router.delete("/api/equipa/membros/{membro_id}")
def remover(membro_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    _no_gabinete(atual, lambda s: svc.remover(s, atual.gabinete_id, atual.utilizador_id, membro_id))
    return {"ok": True}


@router.get("/api/convites/{token}")
def ver(token: str) -> dict:
    return executar(lambda s: svc.ver_convite(s, token))


@router.post("/api/convites/{token}/aceitar")
def aceitar(token: str, corpo: Aceitar, request: Request, response: Response) -> dict:
    ctx = contexto(request)
    sessao = executar(lambda s: svc.aceitar(s, ctx, token, corpo.nome, corpo.password))
    trocar_sessao(request)
    por_cookie(response, sessao, persistente=False)
    return {"ok": True}
