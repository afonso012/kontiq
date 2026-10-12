"""Autenticação: sessões, códigos de verificação, tentativas de entrada.

Tabelas da camada de autenticação, sem Row Level Security (consultadas antes
de se saber o gabinete). O papel da aplicação recebe permissões pelos
privilégios por omissão definidos na 0003.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12 18:55:06.510751+01:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('tentativas_login',
    sa.Column('chave', sa.String(length=300), nullable=False),
    sa.Column('sucesso', sa.Boolean(), nullable=False),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tentativas_login'))
    )
    op.create_index('ix_tentativas_login_chave', 'tentativas_login', ['chave', 'criado_em'], unique=False)
    op.create_table('codigos_verificacao',
    sa.Column('utilizador_id', sa.UUID(), nullable=False),
    sa.Column('finalidade', sa.String(length=20), nullable=False),
    sa.Column('canal', sa.String(length=10), nullable=False),
    sa.Column('destino', sa.String(length=254), nullable=False),
    sa.Column('codigo_hash', sa.String(length=64), nullable=False),
    sa.Column('tentativas', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
    sa.Column('usado_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.CheckConstraint("canal IN ('email', 'sms')", name=op.f('ck_codigos_verificacao_canal')),
    sa.CheckConstraint("finalidade IN ('confirmar_email', 'repor_password', 'entrar_portal')", name=op.f('ck_codigos_verificacao_finalidade')),
    sa.ForeignKeyConstraint(['utilizador_id'], ['utilizadores.id'], name=op.f('fk_codigos_verificacao_utilizador_id_utilizadores'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_codigos_verificacao'))
    )
    op.create_index('ix_codigos_verificacao_destino', 'codigos_verificacao', ['destino', 'finalidade', 'criado_em'], unique=False)
    op.create_index(op.f('ix_codigos_verificacao_utilizador_id'), 'codigos_verificacao', ['utilizador_id'], unique=False)
    op.create_table('sessoes',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('utilizador_id', sa.UUID(), nullable=False),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('gabinete_id', sa.UUID(), nullable=True),
    sa.Column('empresa_id', sa.UUID(), nullable=True),
    sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
    sa.Column('terminada_em', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ultimo_uso', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('user_agent', sa.String(length=300), nullable=True),
    sa.Column('ip', sa.String(length=64), nullable=True),
    sa.Column('criado_em', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.CheckConstraint("(tipo = 'portal') = (empresa_id IS NOT NULL)", name=op.f('ck_sessoes_empresa_so_no_portal')),
    sa.CheckConstraint("tipo IN ('gabinete', 'portal')", name=op.f('ck_sessoes_tipo')),
    sa.ForeignKeyConstraint(['empresa_id'], ['empresas.id'], name=op.f('fk_sessoes_empresa_id_empresas'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['gabinete_id'], ['gabinetes.id'], name=op.f('fk_sessoes_gabinete_id_gabinetes'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['utilizador_id'], ['utilizadores.id'], name=op.f('fk_sessoes_utilizador_id_utilizadores'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessoes')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessoes_token_hash'))
    )
    op.create_index(op.f('ix_sessoes_utilizador_id'), 'sessoes', ['utilizador_id'], unique=False)
    op.add_column('gabinetes', sa.Column('programa_contabilidade', sa.String(length=20), nullable=True))
    op.add_column('gabinetes', sa.Column('dimensao', sa.String(length=20), nullable=True))
    op.add_column('utilizadores', sa.Column('telefone', sa.String(length=20), nullable=True))
    op.add_column('utilizadores', sa.Column('email_confirmado_em', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('programa', 'gabinetes', "programa_contabilidade IN ('toconline', 'primavera', 'phc', 'sage', 'outro')")
    op.create_check_constraint('dimensao', 'gabinetes', "dimensao IN ('ate_20', '21_50', '51_150', 'mais_150')")
    op.create_index('uq_utilizadores_telefone', 'utilizadores', ['telefone'], unique=True, postgresql_where=sa.text('telefone IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('uq_utilizadores_telefone', table_name='utilizadores', postgresql_where=sa.text('telefone IS NOT NULL'))
    op.drop_column('utilizadores', 'email_confirmado_em')
    op.drop_column('utilizadores', 'telefone')
    op.drop_constraint('ck_gabinetes_dimensao', 'gabinetes')
    op.drop_constraint('ck_gabinetes_programa', 'gabinetes')
    op.drop_column('gabinetes', 'dimensao')
    op.drop_column('gabinetes', 'programa_contabilidade')
    op.drop_index(op.f('ix_sessoes_utilizador_id'), table_name='sessoes')
    op.drop_table('sessoes')
    op.drop_index(op.f('ix_codigos_verificacao_utilizador_id'), table_name='codigos_verificacao')
    op.drop_index('ix_codigos_verificacao_destino', table_name='codigos_verificacao')
    op.drop_table('codigos_verificacao')
    op.drop_index('ix_tentativas_login_chave', table_name='tentativas_login')
    op.drop_table('tentativas_login')
