"""Subscrições: ciclo de pagamento, cancelamento no fim do período e pagamentos.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("subscricoes", sa.Column("ciclo", sa.String(10), server_default="mensal", nullable=False))
    op.create_check_constraint("ciclo", "subscricoes", "ciclo IN ('mensal', 'anual')")
    op.add_column("subscricoes", sa.Column("cancelar_no_fim", sa.Boolean(), server_default=sa.text("false"), nullable=False))
    op.create_table(
        "pagamentos_subscricao",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("gabinete_id", sa.UUID(), sa.ForeignKey("gabinetes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plano", sa.String(20), nullable=False),
        sa.Column("ciclo", sa.String(10), nullable=False),
        sa.Column("valor_cents", sa.Integer(), nullable=False),
        sa.Column("iva_cents", sa.Integer(), nullable=False),
        sa.Column("estado", sa.String(10), server_default="pendente", nullable=False),
        sa.Column("fornecedor", sa.String(30), nullable=False),
        sa.Column("referencia", sa.String(120)),
        sa.Column("periodo_inicio", sa.DateTime(timezone=True)),
        sa.Column("periodo_fim", sa.DateTime(timezone=True)),
        sa.Column("criado_por", sa.UUID(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL")),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("pago_em", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("estado IN ('pendente', 'pago', 'falhado', 'anulado')", name="estado"),
        sa.CheckConstraint("ciclo IN ('mensal', 'anual')", name="ciclo"),
    )
    op.create_index("ix_pagamentos_subscricao_gabinete_id", "pagamentos_subscricao", ["gabinete_id"])
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'faturas_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON pagamentos_subscricao TO faturas_app;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("pagamentos_subscricao")
    op.drop_column("subscricoes", "cancelar_no_fim")
    op.drop_constraint("ck_subscricoes_ciclo", "subscricoes")
    op.drop_column("subscricoes", "ciclo")
