"""Empresas-cliente, fornecedores, plano de contas, categorias e regras."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ComDatas, ComId, opcoes
from . import enums as E


class Empresa(ComId, ComDatas, Base):
    """Empresa-cliente de um gabinete (quem envia as faturas)."""

    __tablename__ = "empresas"
    __table_args__ = (
        UniqueConstraint("gabinete_id", "nif"),
        CheckConstraint(f"periodicidade_iva IN ({opcoes(*E.PERIODICIDADE_IVA)})", name="periodicidade_iva"),
        CheckConstraint(f"regime_iva IN ({opcoes(*E.REGIME_IVA)})", name="regime_iva"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    nif: Mapped[str] = mapped_column(String(9))
    email: Mapped[str | None] = mapped_column(String(254))
    telefone: Mapped[str | None] = mapped_column(String(30))
    contacto_nome: Mapped[str | None] = mapped_column(String(200))
    periodicidade_iva: Mapped[str] = mapped_column(String(20), server_default="trimestral")
    regime_iva: Mapped[str] = mapped_column(String(30), server_default="normal")
    # Membro do gabinete responsável por esta empresa.
    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    # Parte local do endereço para onde se reencaminham faturas (ex.: x7k2p9@entrada.faturasemdia.pt).
    caixa_email: Mapped[str] = mapped_column(String(40), unique=True, server_default=text("lower(substr(md5(random()::text), 1, 12))"))
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    notas: Mapped[str | None] = mapped_column(Text)


class Fornecedor(ComId, ComDatas, Base):
    """Fornecedor conhecido pelo gabinete, identificado por país + NIF/VAT."""

    __tablename__ = "fornecedores"
    __table_args__ = (UniqueConstraint("gabinete_id", "pais", "nif"),)

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    pais: Mapped[str] = mapped_column(String(2), server_default="PT")
    nif: Mapped[str] = mapped_column(String(30))
    nome: Mapped[str] = mapped_column(String(200))


class ContaSNC(ComId, Base):
    """Conta do plano de contas. gabinete_id NULL = conta global (base SNC)."""

    __tablename__ = "plano_contas"
    __table_args__ = (
        Index("uq_plano_contas_global", "codigo", unique=True, postgresql_where=text("gabinete_id IS NULL")),
        Index("uq_plano_contas_gabinete", "gabinete_id", "codigo", unique=True, postgresql_where=text("gabinete_id IS NOT NULL")),
    )

    gabinete_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"))
    codigo: Mapped[str] = mapped_column(String(12))
    descricao: Mapped[str] = mapped_column(String(200))
    ativa: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Categoria(ComId, Base):
    """Categoria de despesa legível pelo cliente, com classificação por omissão."""

    __tablename__ = "categorias"
    __table_args__ = (
        CheckConstraint(f"tratamento_iva IN ({opcoes(*E.TRATAMENTOS_IVA)})", name="tratamento_iva"),
        Index("uq_categorias_global", "nome", unique=True, postgresql_where=text("gabinete_id IS NULL")),
        Index("uq_categorias_gabinete", "gabinete_id", "nome", unique=True, postgresql_where=text("gabinete_id IS NOT NULL")),
    )

    gabinete_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"))
    nome: Mapped[str] = mapped_column(String(80))
    conta_codigo: Mapped[str | None] = mapped_column(String(12))
    tratamento_iva: Mapped[str] = mapped_column(String(20), server_default="por_definir")


class RegraFornecedor(ComId, ComDatas, Base):
    """Memória por fornecedor: como classificar as faturas deste fornecedor.

    empresa_id NULL = regra para todas as empresas do gabinete. Uma regra
    específica de uma empresa tem prioridade sobre a regra geral.
    """

    __tablename__ = "regras_fornecedor"
    __table_args__ = (
        UniqueConstraint("fornecedor_id", "empresa_id", postgresql_nulls_not_distinct=True),
        CheckConstraint(f"tratamento_iva IN ({opcoes(*E.TRATAMENTOS_IVA)})", name="tratamento_iva"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    fornecedor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fornecedores.id", ondelete="CASCADE"))
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categorias.id", ondelete="SET NULL"))
    conta_codigo: Mapped[str] = mapped_column(String(12))
    tratamento_iva: Mapped[str] = mapped_column(String(20))
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
