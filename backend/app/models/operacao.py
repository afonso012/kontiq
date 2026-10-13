"""Fecho de períodos, pedidos aos clientes, exportações e registo de atividade."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Identity, Index, Integer, String, Text,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, ComDatas, ComId, opcoes
from . import enums as E


class Periodo(ComId, ComDatas, Base):
    """Estado de um mês de uma empresa (aberto, em revisão, fechado)."""

    __tablename__ = "periodos"
    __table_args__ = (
        UniqueConstraint("empresa_id", "periodo"),
        CheckConstraint(f"estado IN ({opcoes(*E.ESTADOS_PERIODO)})", name="estado"),
        CheckConstraint("periodo = date_trunc('month', periodo)::date", name="periodo_dia_1"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    periodo: Mapped[date] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(String(20), server_default="aberto")
    fechado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PedidoDocumentos(ComId, ComDatas, Base):
    """Pedido de faturas em falta enviado a uma empresa-cliente."""

    __tablename__ = "pedidos_documentos"
    __table_args__ = (
        CheckConstraint(f"canal IN ({opcoes(*E.CANAIS_PEDIDO)})", name="canal"),
        CheckConstraint(f"estado IN ({opcoes(*E.ESTADOS_PEDIDO)})", name="estado"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    periodo: Mapped[date] = mapped_column(Date)
    mensagem: Mapped[str] = mapped_column(Text)
    canal: Mapped[str] = mapped_column(String(20), server_default="email")
    estado: Mapped[str] = mapped_column(String(20), server_default="rascunho")
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Exportacao(ComId, Base):
    """Histórico de exportações (CSV, Excel, ZIP, formatos de software)."""

    __tablename__ = "exportacoes"
    __table_args__ = (CheckConstraint(f"formato IN ({opcoes(*E.FORMATOS_EXPORTACAO)})", name="formato"),)

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    periodo: Mapped[date] = mapped_column(Date)
    formato: Mapped[str] = mapped_column(String(20))
    num_faturas: Mapped[int] = mapped_column(Integer)
    chave_armazenamento: Mapped[str | None] = mapped_column(String(300))
    criado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Uma exportação de várias empresas gera um ficheiro: as linhas partilham o lote.
    lote_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # As faturas ficaram marcadas como exportadas (e bloqueadas)?
    marcou_exportadas: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    desfeita_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RegistoAtividade(Base):
    """Registo de auditoria: quem fez o quê e quando (exigência do RGPD)."""

    __tablename__ = "registo_atividade"
    __table_args__ = (Index("ix_registo_atividade_entidade", "entidade", "entidade_id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    gabinete_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    utilizador_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    entidade: Mapped[str] = mapped_column(String(40))
    entidade_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acao: Mapped[str] = mapped_column(String(40))
    dados: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
