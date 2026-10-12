"""Pedidos de faturas também por SMS.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_pedidos_documentos_canal", "pedidos_documentos")
    op.create_check_constraint("canal", "pedidos_documentos", "canal IN ('email', 'sms', 'whatsapp', 'portal')")


def downgrade() -> None:
    op.drop_constraint("ck_pedidos_documentos_canal", "pedidos_documentos")
    op.create_check_constraint("canal", "pedidos_documentos", "canal IN ('email', 'whatsapp', 'portal')")
