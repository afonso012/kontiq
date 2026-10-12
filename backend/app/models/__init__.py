"""Todos os modelos, importados num só sítio para o Alembic os encontrar."""
from .base import Base
from .contas import (
    AcessoPortal, CodigoVerificacao, Convite, Gabinete, MembroGabinete, Sessao, Subscricao,
    TentativaLogin, Utilizador,
)
from .empresas import Categoria, ContaSNC, Empresa, Fornecedor, RegraFornecedor
from .faturas import Comentario, Documento, Fatura, LinhaIVA, ProblemaFatura
from .operacao import Exportacao, PedidoDocumentos, Periodo, RegistoAtividade

# Tabelas isoladas por gabinete com Row Level Security (ver migração 0003).
# Ficam de fora as tabelas de autenticação (gabinetes, utilizadores, membros_gabinete,
# acessos_portal, convites, subscricoes), consultadas no login antes de haver gabinete.
TABELAS_COM_RLS = (
    "empresas", "fornecedores", "regras_fornecedor", "documentos",
    "faturas", "linhas_iva", "problemas_fatura", "comentarios", "periodos",
    "pedidos_documentos", "exportacoes", "registo_atividade",
)
# Tabelas com linhas globais (gabinete_id NULL) visíveis a todos os gabinetes.
TABELAS_PARTILHADAS = ("plano_contas", "categorias")

__all__ = [
    "Base", "Gabinete", "Utilizador", "MembroGabinete", "AcessoPortal", "Convite", "Subscricao",
    "Sessao", "CodigoVerificacao", "TentativaLogin",
    "Empresa", "Fornecedor", "ContaSNC", "Categoria", "RegraFornecedor",
    "Documento", "Fatura", "LinhaIVA", "ProblemaFatura", "Comentario",
    "Periodo", "PedidoDocumentos", "Exportacao", "RegistoAtividade",
    "TABELAS_COM_RLS", "TABELAS_PARTILHADAS",
]
