"""Dúvidas sobre faturas entre o gabinete e o cliente.

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Quem escreveu: o gabinete ou o cliente (pelo portal).
    op.add_column("comentarios", sa.Column("lado", sa.String(10), server_default="gabinete", nullable=False))
    op.create_check_constraint("lado", "comentarios", "lado IN ('gabinete', 'cliente')")
    # pergunta: o gabinete espera resposta · resposta: o cliente respondeu e o gabinete ainda não viu/fechou.
    op.add_column("faturas", sa.Column("duvida", sa.String(10), nullable=True))
    op.create_check_constraint("duvida", "faturas", "duvida IS NULL OR duvida IN ('pergunta', 'resposta')")


def downgrade() -> None:
    op.drop_constraint("ck_faturas_duvida", "faturas")
    op.drop_column("faturas", "duvida")
    op.drop_constraint("ck_comentarios_lado", "comentarios")
    op.drop_column("comentarios", "lado")
