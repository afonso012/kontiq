"""Testes contra uma base de dados PostgreSQL real, já migrada (alembic upgrade head).

Usa as variáveis DATABASE_URL (papel faturas_app) e MIGRATIONS_DATABASE_URL (dono).
São ignorados se a base de dados não estiver acessível.
"""
import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.core.db import definir_gabinete, sessao_gabinete
from app.models import (
    Categoria, ContaSNC, Empresa, Fatura, Fornecedor, Gabinete, LinhaIVA, RegraFornecedor,
)

APP_URL = os.environ.get("DATABASE_URL")
DONO_URL = os.environ.get("MIGRATIONS_DATABASE_URL")
pytestmark = pytest.mark.skipif(not (APP_URL and DONO_URL), reason="Sem base de dados de teste")


@pytest.fixture(scope="module")
def fabricas():
    dono, app = create_engine(DONO_URL), create_engine(APP_URL)
    yield sessionmaker(bind=dono), sessionmaker(bind=app)
    dono.dispose(); app.dispose()


@pytest.fixture
def dois_gabinetes(fabricas):
    """Cria dois gabinetes (como faria o registo) e limpa no fim."""
    dono, _ = fabricas
    with dono() as s, s.begin():
        a = Gabinete(nome="Gabinete A", nif="514873205")
        b = Gabinete(nome="Gabinete B", nif="516204874")
        s.add_all([a, b]); s.flush()
        ids = (a.id, b.id)
    yield ids
    with dono() as s, s.begin():
        s.execute(text("DELETE FROM gabinetes WHERE id = ANY(:i)"), {"i": list(ids)})


def _criar_fatura(sessao, gab_id, nome_empresa, nif_empresa):
    emp = Empresa(gabinete_id=gab_id, nome=nome_empresa, nif=nif_empresa)
    forn = Fornecedor(gabinete_id=gab_id, nif="507112342", nome="Papelaria do Bonfim, Lda")
    sessao.add_all([emp, forn]); sessao.flush()
    fat = Fatura(gabinete_id=gab_id, empresa_id=emp.id, fornecedor_id=forn.id, periodo=date(2026, 10, 1),
                 tipo_documento="FT", numero="FT A/1", data_emissao=date(2026, 10, 9),
                 nif_fornecedor="507112342", base_total=Decimal("77.90"), iva_total=Decimal("17.92"),
                 total=Decimal("95.82"), metodo_leitura="qr", conta_codigo="6233", tratamento_iva="dedutivel")
    fat.linhas_iva.append(LinhaIVA(gabinete_id=gab_id, tipo_taxa="normal", taxa=Decimal("23"),
                                   base=Decimal("77.90"), iva=Decimal("17.92")))
    sessao.add(fat); sessao.flush()
    sessao.add(RegraFornecedor(gabinete_id=gab_id, fornecedor_id=forn.id, conta_codigo="6233", tratamento_iva="dedutivel"))
    return emp


def test_dados_base_visiveis_a_todos(fabricas, dois_gabinetes):
    _, app = fabricas
    with sessao_gabinete(dois_gabinetes[0], app) as s:
        assert s.scalar(select(func.count()).select_from(ContaSNC)) >= 20
        assert s.scalar(select(Categoria.conta_codigo).where(Categoria.nome == "Combustível")) == "6242"


def test_gabinete_nao_ve_dados_de_outro(fabricas, dois_gabinetes):
    _, app = fabricas
    a, b = dois_gabinetes
    with sessao_gabinete(a, app) as s:
        _criar_fatura(s, a, "Restaurante O Faroleiro", "512173850")
    with sessao_gabinete(b, app) as s:
        _criar_fatura(s, b, "Café Central", "513373853")

    with sessao_gabinete(a, app) as s:
        assert s.scalars(select(Empresa.nome)).all() == ["Restaurante O Faroleiro"]
        assert s.scalar(select(func.count()).select_from(Fatura)) == 1
        assert s.scalar(select(func.count()).select_from(LinhaIVA)) == 1
    with sessao_gabinete(b, app) as s:
        assert s.scalars(select(Empresa.nome)).all() == ["Café Central"]


def test_sem_gabinete_definido_nao_ve_nada(fabricas, dois_gabinetes):
    _, app = fabricas
    with sessao_gabinete(dois_gabinetes[0], app) as s:
        _criar_fatura(s, dois_gabinetes[0], "Clínica Bonfim", "508973856")
    with app() as s:
        assert s.scalar(select(func.count()).select_from(Fatura)) == 0


def test_nao_consegue_escrever_noutro_gabinete(fabricas, dois_gabinetes):
    _, app = fabricas
    a, b = dois_gabinetes
    with pytest.raises(DBAPIError, match="row-level security"):
        with sessao_gabinete(a, app) as s:
            s.add(Empresa(gabinete_id=b, nome="Intrusa", nif="502877642")); s.flush()


def test_regra_unica_por_fornecedor_e_empresa(fabricas, dois_gabinetes):
    """A regra geral (empresa NULL) não pode ser duplicada (NULLS NOT DISTINCT)."""
    _, app = fabricas
    a = dois_gabinetes[0]
    with pytest.raises(DBAPIError, match="uq_regras_fornecedor"):
        with sessao_gabinete(a, app) as s:
            _criar_fatura(s, a, "Oficina Digital", "516204874")
            forn = s.scalar(select(Fornecedor))
            s.add(RegraFornecedor(gabinete_id=a, fornecedor_id=forn.id, conta_codigo="6268", tratamento_iva="dedutivel"))
            s.flush()


def test_periodo_tem_de_ser_dia_1(fabricas, dois_gabinetes):
    _, app = fabricas
    a = dois_gabinetes[0]
    with pytest.raises(DBAPIError, match="periodo_dia_1"):
        with sessao_gabinete(a, app) as s:
            emp = _criar_fatura(s, a, "Pastelaria Sado", "510451284")
            s.add(Fatura(gabinete_id=a, empresa_id=emp.id, periodo=date(2026, 10, 15), metodo_leitura="manual"))
            s.flush()


def test_app_nao_apaga_registo_atividade(fabricas):
    _, app = fabricas
    with pytest.raises(DBAPIError, match="permission denied"):
        with app() as s, s.begin():
            definir_gabinete(s, uuid.uuid4())
            s.execute(text("DELETE FROM registo_atividade"))


def test_nomes_de_restricoes_sem_prefixo_repetido(fabricas):
    """Uma restrição com o prefixo repetido (ck_tabela_ck_tabela_...) impede desfazer migrações."""
    dono = create_engine(os.environ.get("MIGRATIONS_DATABASE_URL") or os.environ["DATABASE_URL"])
    with dono.connect() as c:
        repetidos = c.execute(text(
            "SELECT conname FROM pg_constraint WHERE conname ~ '^(ck|uq|fk|pk|ix)_[a-z_]+_(ck|uq|fk|pk|ix)_'"
        )).scalars().all()
    dono.dispose()
    assert repetidos == []
