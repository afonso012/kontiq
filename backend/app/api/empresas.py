"""Painel do gabinete e empresas-cliente (/api/painel, /api/empresas).

Tudo exige uma sessão de gabinete com o email confirmado e corre isolado no
gabinete dessa sessão (RLS).
"""
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from ..auth.servico import ErroAuth
from ..core.db import sessao_gabinete
from ..empresas import servico as svc
from .auth import SessaoAtual, exigir_gabinete

router = APIRouter(tags=["Painel e empresas"])


def _mes(periodo: str | None) -> date:
    if not periodo:
        return date.today().replace(day=1)
    try:
        ano, mes = (int(x) for x in periodo[:7].split("-"))
        return date(ano, mes, 1)
    except ValueError:
        raise ErroAuth(422, "periodo_invalido", "Período inválido. Use AAAA-MM.")


def _executar(atual: SessaoAtual, fn):
    """Corre `fn(s)` no gabinete da sessão. Erros de validação desfazem tudo."""
    with sessao_gabinete(atual.gabinete_id) as s:
        return fn(s)


@router.get("/api/painel")
def painel(periodo: str | None = Query(None, description="AAAA-MM; por omissão o mês atual"),
           atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Tudo o que o painel precisa: totais do mês, o que precisa de atenção e cada empresa."""
    mes = _mes(periodo)
    return _executar(atual, lambda s: svc.painel(s, uuid.UUID(atual.gabinete_id), mes))


class DadosEmpresa(BaseModel):
    nif: str = Field(max_length=20)
    nome: str = Field(max_length=200)
    periodicidade_iva: str = "trimestral"
    contacto_nome: str | None = Field(default=None, max_length=200)
    telefone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=254)
    convidar: bool = False


def _resumo(e) -> dict:
    return {"id": str(e.id), "nome": e.nome, "nif": e.nif}


@router.post("/api/empresas", status_code=201)
def criar(corpo: DadosEmpresa, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Adiciona uma empresa-cliente e, se pedido, convida o contacto para o portal."""
    return _executar(atual, lambda s: _resumo(svc.criar_empresa(s, atual.gabinete_id, atual.utilizador_id,
                                                                  corpo.model_dump())))


@router.put("/api/empresas/{empresa_id}")
def editar(empresa_id: uuid.UUID, corpo: DadosEmpresa, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _executar(atual, lambda s: _resumo(svc.editar_empresa(s, atual.gabinete_id, atual.utilizador_id,
                                                                   empresa_id, corpo.model_dump())))


@router.post("/api/empresas/{empresa_id}/convite")
def convidar(empresa_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """(Re)envia o convite para o portal ao contacto da empresa."""
    def f(s):
        e = s.get(svc.Empresa, empresa_id)
        if not e:
            raise ErroAuth(404, "nao_encontrada", "Empresa não encontrada.")
        return {"canal": svc.convidar_portal(s, atual.gabinete_id, atual.utilizador_id, e)}
    return _executar(atual, f)


class PedirFaturas(BaseModel):
    periodo: str | None = None


@router.post("/api/empresas/{empresa_id}/pedir-faturas")
def pedir_faturas(empresa_id: uuid.UUID, corpo: PedirFaturas, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Envia ao contacto da empresa um lembrete das faturas do mês em falta."""
    mes = _mes(corpo.periodo)
    return _executar(atual, lambda s: svc.pedir_faturas(s, atual.gabinete_id, atual.utilizador_id, empresa_id, mes))


# ---------------------------------------------------------------- pedidos aos clientes

class PeriodoCorpo(BaseModel):
    periodo: str | None = None


@router.get("/api/pedidos")
def pedidos(periodo: str | None = Query(None), atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    from ..empresas import pedidos as ped
    return _executar(atual, lambda s: ped.listar(s, atual.gabinete_id, _mes(periodo)))


@router.post("/api/pedidos/todas")
def pedir_todas(corpo: PeriodoCorpo, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    from ..empresas import pedidos as ped
    return _executar(atual, lambda s: ped.pedir_a_todas(s, atual.gabinete_id, atual.utilizador_id, _mes(corpo.periodo)))
