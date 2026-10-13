"""Exportações por lote e ligação das faturas ao lote que as exportou.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("exportacoes", sa.Column("lote_id", sa.UUID(), nullable=True))
    op.add_column("exportacoes", sa.Column("marcou_exportadas", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column("exportacoes", sa.Column("desfeita_em", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_exportacoes_lote_id", "exportacoes", ["lote_id"])
    op.add_column("faturas", sa.Column("exportacao_lote", sa.UUID(), nullable=True))
    op.create_index("ix_faturas_exportacao_lote", "faturas", ["exportacao_lote"])


def downgrade() -> None:
    op.drop_index("ix_faturas_exportacao_lote", table_name="faturas")
    op.drop_column("faturas", "exportacao_lote")
    op.drop_index("ix_exportacoes_lote_id", table_name="exportacoes")
    op.drop_column("exportacoes", "desfeita_em")
    op.drop_column("exportacoes", "marcou_exportadas")
    op.drop_column("exportacoes", "lote_id")
