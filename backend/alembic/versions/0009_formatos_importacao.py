"""Formatos de importação: configuração de contas e modelos dos programas.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

FORMATOS_ANTES = ("csv", "xlsx", "zip", "toconline", "primavera", "phc", "sage")
FORMATOS = FORMATOS_ANTES + ("lancamentos", "modelo")


def _lista(xs):
    return ", ".join(f"'{x}'" for x in xs)


def upgrade() -> None:
    op.add_column("gabinetes", sa.Column("config_exportacao", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.drop_constraint("ck_exportacoes_formato", "exportacoes")
    op.create_check_constraint("formato", "exportacoes", f"formato IN ({_lista(FORMATOS)})")
    op.create_table(
        "modelos_exportacao",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("gabinete_id", sa.UUID(), sa.ForeignKey("gabinetes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(80), nullable=False),
        sa.Column("programa", sa.String(20), nullable=False),
        sa.Column("folha", sa.String(80)),
        sa.Column("linha_cabecalho", sa.Integer(), server_default="1", nullable=False),
        sa.Column("cabecalhos", JSONB(), nullable=False),
        sa.Column("mapeamento", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("chave_armazenamento", sa.String(300), nullable=False),
        sa.Column("criado_por", sa.UUID(), sa.ForeignKey("utilizadores.id", ondelete="SET NULL")),
        sa.Column("criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("programa IN ('toconline', 'primavera', 'phc', 'sage', 'outro')", name="programa"),
    )
    op.create_index("ix_modelos_exportacao_gabinete_id", "modelos_exportacao", ["gabinete_id"])
    op.execute("ALTER TABLE modelos_exportacao ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY isolamento_gabinete ON modelos_exportacao USING (gabinete_id = app_gabinete_id()) "
               "WITH CHECK (gabinete_id = app_gabinete_id())")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'faturas_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON modelos_exportacao TO faturas_app;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_table("modelos_exportacao")
    op.drop_constraint("ck_exportacoes_formato", "exportacoes")
    # Os formatos novos são folhas de cálculo: ficam no histórico como xlsx.
    op.execute("UPDATE exportacoes SET formato = 'xlsx' WHERE formato IN ('lancamentos', 'modelo')")
    op.create_check_constraint("formato", "exportacoes", f"formato IN ({_lista(FORMATOS_ANTES)})")
    op.drop_column("gabinetes", "config_exportacao")
