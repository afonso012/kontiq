"""Painel do gabinete e início do portal (versões provisórias, para provar a sessão)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from ..core.db import sessao_gabinete
from ..models import Empresa, Fatura, Gabinete, MembroGabinete, Utilizador
from .auth import SessaoAtual, exigir_gabinete, exigir_portal

router = APIRouter(tags=["Painel"])


@router.get("/api/painel/resumo")
def resumo_gabinete(atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Resumo do gabinete da sessão. Os dados vêm isolados pelo RLS."""
    mes = date.today().replace(day=1)
    with sessao_gabinete(atual.gabinete_id) as s:
        g = s.get(Gabinete, atual.gabinete_id)
        u = s.get(Utilizador, atual.utilizador_id)
        empresas = s.scalar(select(func.count()).select_from(Empresa)) or 0
        faturas = s.scalar(select(func.count()).select_from(Fatura).where(
            Fatura.periodo == mes, Fatura.eliminada_em.is_(None))) or 0
        membros = s.scalar(select(func.count()).select_from(MembroGabinete).where(
            MembroGabinete.gabinete_id == g.id)) or 0
        return {"gabinete": {"nome": g.nome, "nif": g.nif, "programa": g.programa_contabilidade},
                "utilizador": {"nome": u.nome}, "empresas": empresas, "faturas_mes": faturas,
                "membros": membros, "mes": mes.isoformat()}


@router.get("/api/portal/resumo")
def resumo_portal(atual: SessaoAtual = Depends(exigir_portal)) -> dict:
    mes = date.today().replace(day=1)
    with sessao_gabinete(atual.gabinete_id) as s:
        e = s.get(Empresa, atual.empresa_id)
        g = s.get(Gabinete, atual.gabinete_id)
        u = s.get(Utilizador, atual.utilizador_id)
        faturas = s.scalar(select(func.count()).select_from(Fatura).where(
            Fatura.empresa_id == e.id, Fatura.periodo == mes, Fatura.eliminada_em.is_(None))) or 0
        return {"empresa": {"nome": e.nome, "nif": e.nif}, "gabinete": {"nome": g.nome},
                "utilizador": {"nome": u.nome}, "faturas_mes": faturas, "mes": mes.isoformat()}
