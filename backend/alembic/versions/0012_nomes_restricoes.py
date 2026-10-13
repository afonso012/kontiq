"""Corrige nomes de restrições com o prefixo repetido (ck_tabela_ck_tabela_...).

As migrações 0007 a 0009 passavam o nome completo a create_check_constraint, e a
convenção de nomes acrescentava o prefixo outra vez. Funcionava, mas impedia
desfazer essas migrações. Bases criadas de novo já nascem com os nomes certos;
esta migração acerta as que já existiam.

Revision ID: 0012
Revises: 0011
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# tabela, nome errado, nome certo
RENOMEAR = [
    ("comentarios", "ck_comentarios_ck_comentarios_lado", "ck_comentarios_lado"),
    ("faturas", "ck_faturas_ck_faturas_duvida", "ck_faturas_duvida"),
    ("subscricoes", "ck_subscricoes_ck_subscricoes_ciclo", "ck_subscricoes_ciclo"),
    ("pagamentos_subscricao", "ck_pagamentos_subscricao_ck_pagamentos_estado", "ck_pagamentos_subscricao_estado"),
    ("pagamentos_subscricao", "ck_pagamentos_subscricao_ck_pagamentos_ciclo", "ck_pagamentos_subscricao_ciclo"),
    ("modelos_exportacao", "ck_modelos_exportacao_ck_modelos_exportacao_programa", "ck_modelos_exportacao_programa"),
    ("exportacoes", "ck_exportacoes_ck_exportacoes_formato", "ck_exportacoes_formato"),
]


def upgrade() -> None:
    for tabela, errado, certo in RENOMEAR:
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{errado}'
                         AND conrelid = '{tabela}'::regclass) THEN
                ALTER TABLE {tabela} RENAME CONSTRAINT {errado} TO {certo};
              END IF;
            END $$;
        """)


def downgrade() -> None:
    # Os nomes certos servem para as versões anteriores; nada a desfazer.
    pass
