"""Dados base: contas SNC mais usadas em compras/FSE e categorias de despesa.

São linhas globais (gabinete_id NULL), visíveis a todos os gabinetes. Cada
gabinete pode acrescentar as suas próprias contas e categorias.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Subconjunto do código de contas do SNC (classe 3 — compras, classe 6 — FSE).
CONTAS = [
    ("311", "Compras de mercadorias"),
    ("312", "Compras de matérias-primas, subsidiárias e de consumo"),
    ("621", "Subcontratos"),
    ("6221", "Trabalhos especializados"),
    ("6222", "Publicidade e propaganda"),
    ("6223", "Vigilância e segurança"),
    ("6224", "Honorários"),
    ("6225", "Comissões"),
    ("6226", "Conservação e reparação"),
    ("6228", "Outros serviços especializados"),
    ("6231", "Ferramentas e utensílios de desgaste rápido"),
    ("6232", "Livros e documentação técnica"),
    ("6233", "Material de escritório"),
    ("6234", "Artigos para oferta"),
    ("6241", "Eletricidade"),
    ("6242", "Combustíveis"),
    ("6243", "Água"),
    ("6248", "Outros (energia e fluidos)"),
    ("6251", "Deslocações e estadas"),
    ("6252", "Transportes de pessoal"),
    ("6253", "Transportes de mercadorias"),
    ("6261", "Rendas e alugueres"),
    ("6262", "Comunicação"),
    ("6263", "Seguros"),
    ("6265", "Contencioso e notariado"),
    ("6266", "Despesas de representação"),
    ("6267", "Limpeza, higiene e conforto"),
    ("6268", "Outros serviços"),
]

# Categoria → (conta sugerida, tratamento do IVA sugerido). São só sugestões:
# o contabilista confirma e a memória por fornecedor guarda a decisão.
CATEGORIAS = [
    ("Mercadorias", "311", "dedutivel"),
    ("Matérias-primas e consumo", "312", "dedutivel"),
    ("Material de escritório", "6233", "dedutivel"),
    ("Software e subscrições", "6268", "dedutivel"),
    ("Publicidade", "6222", "dedutivel"),
    ("Combustível", "6242", "dedutivel_50"),
    ("Comunicações", "6262", "dedutivel"),
    ("Eletricidade", "6241", "dedutivel"),
    ("Água", "6243", "dedutivel"),
    ("Rendas e alugueres", "6261", "por_definir"),
    ("Refeições", "6251", "nao_dedutivel"),
    ("Deslocações e estadas", "6251", "nao_dedutivel"),
    ("Serviços profissionais", "6221", "dedutivel"),
    ("Honorários", "6224", "dedutivel"),
    ("Conservação e reparação", "6226", "dedutivel"),
    ("Seguros", "6263", "isento"),
    ("Limpeza e higiene", "6267", "dedutivel"),
    ("Outros", "6268", "por_definir"),
]


def upgrade() -> None:
    contas = sa.table("plano_contas", sa.column("codigo", sa.String), sa.column("descricao", sa.String))
    op.bulk_insert(contas, [{"codigo": c, "descricao": d} for c, d in CONTAS])
    cats = sa.table(
        "categorias", sa.column("nome", sa.String), sa.column("conta_codigo", sa.String),
        sa.column("tratamento_iva", sa.String),
    )
    op.bulk_insert(cats, [{"nome": n, "conta_codigo": c, "tratamento_iva": t} for n, c, t in CATEGORIAS])


def downgrade() -> None:
    op.execute("DELETE FROM categorias WHERE gabinete_id IS NULL")
    op.execute("DELETE FROM plano_contas WHERE gabinete_id IS NULL")
