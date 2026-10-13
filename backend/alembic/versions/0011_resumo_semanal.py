"""Preferência do resumo semanal por email (por pessoa e gabinete).

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("membros_gabinete", sa.Column("resumo_semanal", sa.Boolean(), server_default=sa.text("true"), nullable=False))
    op.add_column("membros_gabinete", sa.Column("resumo_enviado_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("membros_gabinete", "resumo_enviado_em")
    op.drop_column("membros_gabinete", "resumo_semanal")
