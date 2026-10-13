"""Linhas importadas do e-Fatura (faturas de aquisição) para cruzar com as faturas recebidas.

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "efatura_linhas",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("gabinete_id", sa.UUID(), sa.ForeignKey("gabinetes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.UUID(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("periodo", sa.Date(), nullable=False),
        sa.Column("nif_emitente", sa.String(20), nullable=False),
        sa.Column("nome_emitente", sa.String(200)),
        sa.Column("numero", sa.String(120), nullable=False),
        sa.Column("atcud", sa.String(120)),
        sa.Column("tipo", sa.String(40)),
        sa.Column("data_emissao", sa.Date(), nullable=False),
        sa.Column("total", sa.Numeric(14, 2)),
        sa.Column("iva", sa.Numeric(14, 2)),
        sa.Column("base", sa.Numeric(14, 2)),
        sa.Column("situacao", sa.String(60)),
        sa.Column("importado_por", sa.UUID(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL")),
        sa.Column("importado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_efatura_linhas_empresa_periodo", "efatura_linhas", ["empresa_id", "periodo"])
    op.execute("ALTER TABLE efatura_linhas ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY isolamento_gabinete ON efatura_linhas USING (gabinete_id = app_gabinete_id()) "
               "WITH CHECK (gabinete_id = app_gabinete_id())")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'faturas_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON efatura_linhas TO faturas_app;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("efatura_linhas")
