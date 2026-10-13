"""Subscrição do gabinete (/api/subscricao)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..core.db import sessao_gabinete
from ..subscricoes import servico as svc
from .auth import SessaoAtual, exigir_gabinete

router = APIRouter(prefix="/api/subscricao", tags=["Subscrição"])


class Escolha(BaseModel):
    plano: str
    ciclo: str = "mensal"


class Simulacao(BaseModel):
    sucesso: bool = True


def _no_gabinete(atual: SessaoAtual, fn):
    with sessao_gabinete(atual.gabinete_id) as s:
        return fn(s)


@router.get("")
def ver(atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: svc.detalhe(s, atual.gabinete_id, atual.utilizador_id))


@router.post("/pagamentos", status_code=201)
def escolher(corpo: Escolha, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Começa o pagamento de um plano. Devolve o endereço da página de pagamento."""
    return _no_gabinete(atual, lambda s: svc.iniciar_pagamento(s, atual.gabinete_id, atual.utilizador_id, corpo.plano, corpo.ciclo))


@router.get("/pagamentos/{pagamento_id}")
def pagamento(pagamento_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: svc.ver_pagamento(s, atual.gabinete_id, pagamento_id))


@router.post("/pagamentos/{pagamento_id}/simular")
def simular(pagamento_id: uuid.UUID, corpo: Simulacao, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Só no modo simulado: dá o pagamento como feito (ou falhado)."""
    return _no_gabinete(atual, lambda s: svc.confirmar_simulado(s, atual.gabinete_id, atual.utilizador_id, pagamento_id, corpo.sucesso))


@router.post("/cancelar")
def cancelar(atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: svc.cancelar(s, atual.gabinete_id, atual.utilizador_id))


@router.post("/retomar")
def retomar(atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: svc.retomar(s, atual.gabinete_id, atual.utilizador_id))
