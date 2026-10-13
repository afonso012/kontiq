"""Documentos, faturas, linhas de IVA e problemas detetados."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Numeric, String, Text,
    UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ComDatas, ComId, Dinheiro, opcoes
from . import enums as E


class Documento(ComId, Base):
    """Ficheiro original (PDF/imagem) guardado no armazenamento de objetos (S3)."""

    __tablename__ = "documentos"
    __table_args__ = (
        # O mesmo ficheiro enviado duas vezes para a mesma empresa é detetado logo.
        UniqueConstraint("empresa_id", "sha256"),
        CheckConstraint(f"canal IN ({opcoes(*E.CANAIS_DOCUMENTO)})", name="canal"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    chave_armazenamento: Mapped[str] = mapped_column(String(300), unique=True)
    nome_original: Mapped[str] = mapped_column(String(255))
    tipo_mime: Mapped[str] = mapped_column(String(100))
    tamanho_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    canal: Mapped[str] = mapped_column(String(20))
    enviado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    email_remetente: Mapped[str | None] = mapped_column(String(254))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Fatura(ComId, ComDatas, Base):
    """Fatura de compra/despesa de uma empresa-cliente."""

    __tablename__ = "faturas"
    __table_args__ = (
        CheckConstraint(f"tipo_documento IN ({opcoes(*E.TIPOS_DOCUMENTO)})", name="tipo_documento"),
        CheckConstraint(f"metodo_leitura IN ({opcoes(*E.METODOS_LEITURA)})", name="metodo_leitura"),
        CheckConstraint(f"estado IN ({opcoes(*E.ESTADOS_FATURA)})", name="estado"),
        CheckConstraint(f"tratamento_iva IN ({opcoes(*E.TRATAMENTOS_IVA)})", name="tratamento_iva"),
        CheckConstraint(f"origem_classificacao IN ({opcoes(*E.ORIGENS_CLASSIFICACAO)})", name="origem_classificacao"),
        CheckConstraint("periodo = date_trunc('month', periodo)::date", name="periodo_dia_1"),
        CheckConstraint("confianca IS NULL OR (confianca >= 0 AND confianca <= 1)", name="confianca"),
        Index("ix_faturas_empresa_periodo", "empresa_id", "periodo"),
        Index("ix_faturas_gabinete_estado", "gabinete_id", "estado"),
        # Para detetar duplicados (mesmo fornecedor + mesmo número na mesma empresa).
        Index("ix_faturas_duplicados", "empresa_id", "nif_fornecedor", "numero"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"))
    empresa_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("empresas.id", ondelete="CASCADE"))
    documento_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("documentos.id", ondelete="SET NULL"))
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fornecedores.id", ondelete="SET NULL"), index=True)

    # Mês contabilístico a que a fatura pertence (sempre dia 1).
    periodo: Mapped[date] = mapped_column(Date)

    # Identificação do documento.
    tipo_documento: Mapped[str] = mapped_column(String(10), server_default="FT")
    numero: Mapped[str | None] = mapped_column(String(80))
    atcud: Mapped[str | None] = mapped_column(String(80))
    data_emissao: Mapped[date | None] = mapped_column(Date)
    nif_fornecedor: Mapped[str | None] = mapped_column(String(30))
    pais_fornecedor: Mapped[str] = mapped_column(String(2), server_default="PT")
    nif_adquirente: Mapped[str | None] = mapped_column(String(30))

    # Valores na moeda do documento + conversão para euros.
    moeda: Mapped[str] = mapped_column(String(3), server_default="EUR")
    taxa_cambio: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    base_total: Mapped[Decimal] = mapped_column(Dinheiro, server_default="0")
    iva_total: Mapped[Decimal] = mapped_column(Dinheiro, server_default="0")
    total: Mapped[Decimal] = mapped_column(Dinheiro, server_default="0")
    total_eur: Mapped[Decimal | None] = mapped_column(Dinheiro)

    # Como foi lida.
    metodo_leitura: Mapped[str] = mapped_column(String(10))
    confianca: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    qr_texto: Mapped[str | None] = mapped_column(Text)
    dados_extraidos: Mapped[dict | None] = mapped_column(JSONB)

    # Classificação contabilística.
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categorias.id", ondelete="SET NULL"))
    conta_codigo: Mapped[str | None] = mapped_column(String(12))
    tratamento_iva: Mapped[str] = mapped_column(String(20), server_default="por_definir")
    origem_classificacao: Mapped[str] = mapped_column(String(10), server_default="sugestao")

    # Fluxo de trabalho.
    estado: Mapped[str] = mapped_column(String(20), server_default="por_conferir")
    conferida_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    conferida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notas: Mapped[str | None] = mapped_column(Text)
    eliminada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Lote da exportação que a levou para o programa de contabilidade.
    exportacao_lote: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    # Dúvida com o cliente: None, "pergunta" (à espera do cliente) ou "resposta" (o cliente respondeu).
    duvida: Mapped[str | None] = mapped_column(String(10))

    linhas_iva: Mapped[list["LinhaIVA"]] = relationship(back_populates="fatura", cascade="all, delete-orphan")
    problemas: Mapped[list["ProblemaFatura"]] = relationship(back_populates="fatura", cascade="all, delete-orphan")


class LinhaIVA(ComId, Base):
    """Uma linha do resumo de IVA da fatura (por espaço fiscal e taxa).

    Permite faturas com várias taxas e faturas dos Açores e da Madeira.
    """

    __tablename__ = "linhas_iva"
    __table_args__ = (
        CheckConstraint(f"espaco_fiscal IN ({opcoes(*E.ESPACOS_FISCAIS)})", name="espaco_fiscal"),
        CheckConstraint(f"tipo_taxa IN ({opcoes(*E.TIPOS_TAXA)})", name="tipo_taxa"),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"))
    fatura_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("faturas.id", ondelete="CASCADE"), index=True)
    espaco_fiscal: Mapped[str] = mapped_column(String(5), server_default="PT")
    tipo_taxa: Mapped[str] = mapped_column(String(15))
    # Percentagem calculada (iva / base). Não se guarda uma tabela de taxas fixa.
    taxa: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    base: Mapped[Decimal] = mapped_column(Dinheiro)
    iva: Mapped[Decimal] = mapped_column(Dinheiro, server_default="0")

    fatura: Mapped[Fatura] = relationship(back_populates="linhas_iva")


class ProblemaFatura(ComId, Base):
    """Problema detetado pelas validações (duplicado, NIF inválido, etc.)."""

    __tablename__ = "problemas_fatura"
    __table_args__ = (
        CheckConstraint(f"nivel IN ({opcoes(*E.NIVEIS_PROBLEMA)})", name="nivel"),
        # Só pode existir um problema aberto de cada tipo por fatura.
        Index("uq_problemas_abertos", "fatura_id", "codigo", unique=True, postgresql_where=text("NOT resolvido")),
    )

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"))
    fatura_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("faturas.id", ondelete="CASCADE"), index=True)
    codigo: Mapped[str] = mapped_column(String(40))
    nivel: Mapped[str] = mapped_column(String(10))
    mensagem: Mapped[str] = mapped_column(Text)
    resolvido: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    resolvido_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    resolvido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    fatura: Mapped[Fatura] = relationship(back_populates="problemas")


class Comentario(ComId, Base):
    """Conversa sobre uma fatura entre o gabinete e o cliente."""

    __tablename__ = "comentarios"

    gabinete_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("gabinetes.id", ondelete="CASCADE"))
    fatura_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("faturas.id", ondelete="CASCADE"), index=True)
    autor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("utilizadores.id", ondelete="SET NULL"))
    lado: Mapped[str] = mapped_column(String(10), server_default="gabinete")
    texto: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
