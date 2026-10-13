"""Arranque em produção: registos (logs), Sentry opcional e verificação da configuração.

- Em produção os registos saem em JSON, uma linha por evento (fáceis de ler com `docker compose logs`
  ou de enviar para outro serviço). Em desenvolvimento ficam em texto simples.
- Com SENTRY_DSN definido (e o pacote sentry-sdk instalado), os erros vão também para o Sentry.
- Em produção a aplicação recusa arrancar com configurações perigosas (chave secreta por omissão,
  pagamentos simulados, endereço público sem HTTPS).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

from .config import get_settings


class _Json(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        d = {"em": datetime.fromtimestamp(r.created, timezone.utc).isoformat(timespec="milliseconds"),
             "nivel": r.levelname, "origem": r.name, "mensagem": r.getMessage()}
        if r.exc_info:
            d["erro"] = self.formatException(r.exc_info)
        return json.dumps(d, ensure_ascii=False)


def configurar_registos() -> None:
    s = get_settings()
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(_Json() if s.producao else logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    raiz = logging.getLogger()
    raiz.handlers[:] = [h]
    raiz.setLevel(os.environ.get("NIVEL_REGISTOS", "INFO"))
    dsn = os.environ.get("SENTRY_DSN")
    if dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=dsn, environment=s.ambiente, traces_sample_rate=0.0, send_default_pii=False)
        except ImportError:
            logging.getLogger("faturas").warning("SENTRY_DSN definido mas o pacote sentry-sdk não está instalado.")


class ConfiguracaoInsegura(RuntimeError):
    pass


def verificar_configuracao() -> None:
    s = get_settings()
    if not s.producao:
        return
    problemas = []
    if s.secret_key in ("mudar-em-producao", "teste") or len(s.secret_key) < 32:
        problemas.append("SECRET_KEY tem de ter pelo menos 32 caracteres aleatórios (gere com: openssl rand -hex 32).")
    if s.pagamentos_modo == "simulado":
        problemas.append("PAGAMENTOS_MODO=simulado não é permitido em produção (use 'desligado' até haver fornecedor).")
    if not s.url_publica.startswith("https://"):
        problemas.append("URL_PUBLICA tem de começar por https:// em produção.")
    if "faturas_app:faturas_app@" in s.database_url or "faturas:faturas@" in s.migrations_database_url:
        problemas.append("As palavras-passe da base de dados ainda são as de desenvolvimento.")
    if problemas:
        raise ConfiguracaoInsegura("Configuração de produção insegura:\n- " + "\n- ".join(problemas))
    if s.sms_modo == "simulado":
        logging.getLogger("faturas").warning(
            "SMS_MODO=simulado: os SMS não são enviados. Os clientes do portal devem entrar com código por email.")
    if s.ia_modo == "teste":
        logging.getLogger("faturas").warning("IA_MODO=teste: faturas sem QR lidas só por regras sobre o texto do PDF.")
