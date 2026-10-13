"""Envio de emails e SMS.

Em desenvolvimento os emails vão para o Mailpit (http://localhost:8025), uma
caixa de correio de teste que corre no próprio computador. Os SMS são
simulados: aparecem no terminal e também no Mailpit, como um email para
"sms-<número>@telemovel.local". Se o Mailpit não estiver a correr, a
mensagem fica só no terminal, para não bloquear quem está a testar.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from html import escape

from .config import get_settings

log = logging.getLogger("faturas.envio")


def _html(titulo: str, paragrafos: list[str], codigo: str | None) -> str:
    bloco = (f'<p style="font:600 32px/1 ui-monospace,Menlo,monospace;letter-spacing:8px;'
             f'margin:24px 0;color:#0e1121">{escape(codigo)}</p>') if codigo else ""
    corpo = "".join(f'<p style="margin:0 0 12px;color:#5b6075">{escape(p)}</p>' for p in paragrafos)
    return (
        '<div style="background:#f5f6fa;padding:32px 16px;font-family:system-ui,sans-serif">'
        '<div style="max-width:480px;margin:0 auto;background:#fff;border:1px solid #e3e6ef;'
        'border-radius:20px;padding:32px">'
        '<p style="margin:0 0 24px;font-weight:600;color:#0e1121">Kontiq</p>'
        f'<h1 style="margin:0 0 12px;font-size:24px;font-weight:500;color:#0e1121">{escape(titulo)}</h1>'
        f"{corpo}{bloco}</div></div>"
    )


def enviar_email(destino: str, assunto: str, titulo: str, paragrafos: list[str], codigo: str | None = None) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.email_remetente
    msg["To"] = destino
    msg["Subject"] = assunto
    texto = "\n\n".join([titulo, *paragrafos] + ([f"Código: {codigo}"] if codigo else []))
    msg.set_content(texto)
    msg.add_alternative(_html(titulo, paragrafos, codigo), subtype="html")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=5) as smtp:
            if s.smtp_tls:
                smtp.starttls()
            if s.smtp_utilizador:
                smtp.login(s.smtp_utilizador, s.smtp_password)
            smtp.send_message(msg)
        return True
    except OSError as e:
        if s.producao:
            log.error("Falha a enviar email para %s: %s", destino, e)
            raise
        # Desenvolvimento sem Mailpit: mostrar no terminal para se poder continuar.
        links = " ".join(p for p in paragrafos if "://" in p)
        log.warning("Mailpit indisponível (%s). Email para %s — %s%s%s", e, destino, assunto,
                    f" — CÓDIGO {codigo}" if codigo else "", f" — {links}" if links else "")
        return False


def enviar_sms(numero: str, texto: str) -> None:
    s = get_settings()
    if s.sms_modo != "simulado":
        raise NotImplementedError("Envio real de SMS ainda não configurado.")
    log.warning("SMS simulado para %s: %s", numero, texto)
    enviar_email(f"sms-{numero.lstrip('+')}@telemovel.local", f"SMS para {numero}", "SMS (simulado)", [texto])
