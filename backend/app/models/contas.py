"""Gabinetes, utilizadores, acessos e subscrições (camada de autenticação).

Estas tabelas NÃO têm Row Level Security: são consultadas no login, antes de
se saber a que gabinete o pedido pertence.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ComDatas, ComId, opcoes
from . import enums as E


class Gabinete(ComId, ComDatas, Base):
    """Um gabinete de contabilidade: o cliente que paga a subscrição (tenant)."""

    __tablename__ = "gabinetes"
    __table_args__ = (
        CheckConstraint(f"plano IN ({opcoes(*E.PLANOS)})", name="plano"),
        CheckConstraint(f"estado IN ({opcoes(*E.ESTADOS_GABINETE)})", name="estado"),
    )

    nome: Mapped[str] = mapped_column(String(200))
    nif: Mapped[str] = mapped_column(String(9), unique=True)
    email: Mapped[str | None] = mapped_column(String(254))
    telefone: Mapped[str | None] = mapped_column(String(30))
    plano: Mapped[str] = mapped_column(String(20), server_default="arranque")
    estado: Mapped[str] = mapped_column(String(20), server_default="ativo")

    membros: Mapped[list["MembroGabinete"]] = relationship(back_populates="gabinete")


class Utilizador(ComId, ComDatas, Base):
    """Qualquer pessoa que entra na plataforma: contabilista ou cliente."""

    __tablename__ = "utilizadores"
    __table_args__ = (Index("uq_utilizadores_email_lower", func.lower(text("email")), unique=True),)

    email: Mapped[str] = mapped_column(String(254))
    nome: Mapped[str] = mapped_column(String(200))
    # Pode ficar vazio se a pessoa só entrar por link mágico enviado por email.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MembroGabinete(ComId, ComDatas, Base):
    """Ligação utilizador ↔ gabinete, com o papel dentro do gabinete."""

    __tablename__ = "membros_gabinete"
    __table_args__ = (
        UniqueConstraint("gabinete_id", "utilizador_id"),
        CheckConstraint(f"papel IN ({opcoes(*E.PAPEIS_GABINETE)})", name="papel"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"))
    utilizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="CASCADE"), index=True)
    papel: Mapped[str] = mapped_column(String(20), server_default="colaborador")

    gabinete: Mapped[Gabinete] = relationship(back_populates="membros")


class AcessoPortal(ComId, ComDatas, Base):
    """Acesso de uma pessoa da empresa-cliente ao portal dessa empresa."""

    __tablename__ = "acessos_portal"
    __table_args__ = (
        UniqueConstraint("empresa_id", "utilizador_id"),
        CheckConstraint(f"papel IN ({opcoes(*E.PAPEIS_PORTAL)})", name="papel"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    utilizador_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="CASCADE"), index=True)
    papel: Mapped[str] = mapped_column(String(20), server_default="colaborador")


class Convite(ComId, Base):
    """Convite por email para um colaborador do gabinete ou um cliente do portal."""

    __tablename__ = "convites"
    __table_args__ = (
        CheckConstraint(
            f"papel IN ({opcoes(*E.PAPEIS_GABINETE, *E.PAPEIS_PORTAL)})", name="papel"
        ),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    # Preenchido quando o convite é para o portal de uma empresa-cliente.
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(254))
    papel: Mapped[str] = mapped_column(String(20))
    # Guardamos só o hash do token; o token em claro vai apenas no email.
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    convidado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    aceite_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscricao(ComId, ComDatas, Base):
    """Plano pago pelo gabinete. Uma subscrição ativa por gabinete."""

    __tablename__ = "subscricoes"
    __table_args__ = (
        CheckConstraint(f"plano IN ({opcoes(*E.PLANOS)})", name="plano"),
        CheckConstraint(f"estado IN ({opcoes(*E.ESTADOS_SUBSCRICAO)})", name="estado"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), unique=True)
    plano: Mapped[str] = mapped_column(String(20))
    estado: Mapped[str] = mapped_column(String(20), server_default="teste")
    limite_empresas: Mapped[int] = mapped_column(Integer)
    # Preço acordado em cêntimos (permite descontos de "gabinete fundador").
    preco_mensal_cents: Mapped[int] = mapped_column(Integer)
    fim_teste: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    proxima_renovacao: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fornecedor_pagamento: Mapped[str | None] = mapped_column(String(30))
    referencia_externa: Mapped[str | None] = mapped_column(String(120))
    notas: Mapped[str | None] = mapped_column(Text)
