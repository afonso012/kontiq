"""Arranque em produção: configurações perigosas são recusadas."""
import pytest

from app.core import config, producao


def _com(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()


def test_recusa_configuracao_insegura(monkeypatch):
    _com(monkeypatch, AMBIENTE="producao", SECRET_KEY="curta", PAGAMENTOS_MODO="simulado", URL_PUBLICA="http://x.pt")
    try:
        with pytest.raises(producao.ConfiguracaoInsegura) as e:
            producao.verificar_configuracao()
        msg = str(e.value)
        assert "SECRET_KEY" in msg and "PAGAMENTOS_MODO" in msg and "https" in msg
    finally:
        config.get_settings.cache_clear()


def test_aceita_configuracao_correta(monkeypatch):
    _com(monkeypatch, AMBIENTE="producao", SECRET_KEY="a" * 64, PAGAMENTOS_MODO="desligado", URL_PUBLICA="https://kontiq.pt",
         DATABASE_URL="postgresql+psycopg://faturas_app:segredo1@db/faturas",
         MIGRATIONS_DATABASE_URL="postgresql+psycopg://faturas:segredo2@db/faturas")
    try:
        producao.verificar_configuracao()
    finally:
        config.get_settings.cache_clear()
