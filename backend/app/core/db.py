"""Ligação à base de dados e isolamento por gabinete.

Cada pedido abre uma sessão com `sessao_gabinete(gabinete_id)`. Isso define a
variável `app.gabinete_id` só para a transação atual, e as políticas de Row
Level Security do PostgreSQL garantem que só se vêem e escrevem linhas desse
gabinete — mesmo que uma consulta no código se esqueça de filtrar.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def definir_gabinete(sessao: Session, gabinete_id: uuid.UUID | str) -> None:
    """Fixa o gabinete da transação atual (válido até ao commit/rollback)."""
    sessao.execute(
        text("SELECT set_config('app.gabinete_id', :g, true)"), {"g": str(gabinete_id)}
    )


@contextmanager
def sessao_gabinete(gabinete_id: uuid.UUID | str, fabrica: sessionmaker = SessionLocal) -> Iterator[Session]:
    """Sessão já isolada no gabinete indicado. Faz commit no fim ou rollback se falhar."""
    with fabrica() as sessao:
        with sessao.begin():
            definir_gabinete(sessao, gabinete_id)
            yield sessao


@contextmanager
def sessao_sem_gabinete(fabrica: sessionmaker = SessionLocal) -> Iterator[Session]:
    """Sessão para login e convites (tabelas de contas, sem RLS)."""
    with fabrica() as sessao:
        with sessao.begin():
            yield sessao
