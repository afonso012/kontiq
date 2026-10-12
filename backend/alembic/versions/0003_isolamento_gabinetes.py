"""Isolamento entre gabinetes com Row Level Security (RLS) do PostgreSQL.

A aplicação liga-se com o papel `faturas_app` (sem ser dono das tabelas). Em
cada transação define `app.gabinete_id`; as políticas abaixo fazem com que
só veja e escreva linhas desse gabinete. Se a variável não estiver definida,
não vê nada. As migrações correm com o dono das tabelas, que não é afetado.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Copiado (não importado) de app.models para a migração não mudar se o código mudar.
TABELAS_COM_RLS = (
    "empresas", "fornecedores", "regras_fornecedor", "documentos",
    "faturas", "linhas_iva", "problemas_fatura", "comentarios", "periodos",
    "pedidos_documentos", "exportacoes", "registo_atividade",
)
TABELAS_PARTILHADAS = ("plano_contas", "categorias")
PAPEL_APP = "faturas_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION app_gabinete_id() RETURNS uuid
        LANGUAGE sql STABLE AS $$
            SELECT nullif(current_setting('app.gabinete_id', true), '')::uuid
        $$;
        """
    )
    for t in TABELAS_COM_RLS:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY isolamento_gabinete ON {t} "
            f"USING (gabinete_id = app_gabinete_id()) "
            f"WITH CHECK (gabinete_id = app_gabinete_id())"
        )
    for t in TABELAS_PARTILHADAS:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY isolamento_gabinete ON {t} "
            f"USING (gabinete_id IS NULL OR gabinete_id = app_gabinete_id()) "
            f"WITH CHECK (gabinete_id = app_gabinete_id())"
        )
    # Permissões do papel da aplicação (criado em docker/postgres/init.sql).
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PAPEL_APP}') THEN
                GRANT USAGE ON SCHEMA public TO {PAPEL_APP};
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {PAPEL_APP};
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {PAPEL_APP};
                GRANT EXECUTE ON FUNCTION app_gabinete_id() TO {PAPEL_APP};
                REVOKE ALL ON TABLE alembic_version FROM {PAPEL_APP};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {PAPEL_APP};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                    GRANT USAGE, SELECT ON SEQUENCES TO {PAPEL_APP};
            END IF;
        END $$;
        """
    )
    # O registo de atividade é só de acrescentar: a aplicação não altera nem apaga.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PAPEL_APP}') THEN
                REVOKE UPDATE, DELETE ON TABLE registo_atividade FROM {PAPEL_APP};
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for t in TABELAS_COM_RLS + TABELAS_PARTILHADAS:
        op.execute(f"DROP POLICY IF EXISTS isolamento_gabinete ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS app_gabinete_id()")
