"""Resumo semanal por email para as pessoas do gabinete.

Uma vez por semana (segunda de manhã), cada pessoa com o resumo ligado recebe:
respostas dos clientes por ver, faturas por conferir e com problemas, empresas sem faturas
do mês, faturas em falta do e-Fatura e o que chegou na última semana.
Só se envia se houver alguma coisa para fazer.

Correr à mão ou num agendamento (cron/launchd):
    python -m app.resumo            # envia a quem ainda não recebeu nos últimos 6 dias
    python -m app.resumo --forcar   # envia já a todos (testes)
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timedelta, timezone
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .core.config import get_settings
from .core.db import sessao_gabinete, sessao_sem_gabinete
from .core.envio import enviar_email
from .empresas.servico import MESES, painel
from .models import Documento, Gabinete, MembroGabinete, Utilizador

log = logging.getLogger("faturas.resumo")
INTERVALO = timedelta(days=6)


def agora() -> datetime:
    return datetime.now(timezone.utc)


def dados(s: Session, gabinete_id, hoje: date | None = None) -> dict:
    """Os números do resumo. Nos primeiros dias do mês olha para o mês anterior (é o que se está a fechar)."""
    hoje = hoje or date.today()
    mes = (hoje.replace(day=1) - timedelta(days=1)).replace(day=1) if hoje.day <= 10 else hoje.replace(day=1)
    p = painel(s, gabinete_id, mes)
    respostas = [a for a in p["atencao"] if a["codigo"] == "cliente_respondeu"]
    efatura = [a for a in p["atencao"] if a["codigo"] == "efatura_em_falta"]
    sem = [e for e in p["empresas"] if e["estado"] == "none"]
    semana = s.scalar(select(func.count()).select_from(Documento).where(Documento.criado_em >= agora() - timedelta(days=7))) or 0
    portal = s.scalar(select(func.count()).select_from(Documento).where(
        Documento.criado_em >= agora() - timedelta(days=7), Documento.canal == "portal")) or 0
    return {
        "mes": mes, "mes_txt": f"{MESES[mes.month - 1]} de {mes.year}", "gabinete": p["gabinete"]["nome"],
        "pct": p["totais"]["pct_conferido"], "por_conferir": p["totais"]["por_conferir"], "problemas": p["totais"]["problemas"],
        "respostas": len(respostas), "respostas_empresas": [a["empresa"] for a in respostas],
        "sem_faturas": [e["nome"] for e in sem], "efatura": sum(int(a["titulo"].split()[1]) for a in efatura),
        "recebidos_semana": semana, "recebidos_portal": portal, "empresas": p["totais"]["empresas"],
    }


def ha_algo(d: dict) -> bool:
    return any((d["respostas"], d["por_conferir"], d["problemas"], d["sem_faturas"], d["efatura"], d["recebidos_semana"]))


def _linha(n, texto: str, url: str, cor: str = "#0e1121") -> str:
    return (f'<tr><td style="padding:12px 0;border-top:1px solid #e3e6ef;width:56px;font:600 22px/1 ui-monospace,Menlo,monospace;'
            f'color:{cor}">{n}</td><td style="padding:12px 0;border-top:1px solid #e3e6ef;color:#0e1121">{texto}</td>'
            f'<td style="padding:12px 0;border-top:1px solid #e3e6ef;text-align:right"><a href="{url}" '
            f'style="color:#4353e8;text-decoration:none;font-weight:500">Ver →</a></td></tr>')


def mensagem(d: dict, nome: str) -> tuple[str, str, list[str]]:
    """(assunto, html, texto simples)."""
    base = get_settings().url_publica.rstrip("/")
    periodo = d["mes"].strftime("%Y-%m")
    linhas, texto = [], []
    if d["respostas"]:
        quem = ", ".join(d["respostas_empresas"][:3])
        linhas.append(_linha(d["respostas"], f"{'cliente respondeu' if d['respostas'] == 1 else 'clientes responderam'} às suas dúvidas "
                             f"<span style='color:#5b6075'>({escape(quem)})</span>", f"{base}/pedidos", "#4353e8"))
        texto.append(f"{d['respostas']} respostas de clientes por ver ({quem}).")
    if d["por_conferir"]:
        linhas.append(_linha(d["por_conferir"], f"{'fatura' if d['por_conferir'] == 1 else 'faturas'} por conferir"
                             + (f" <span style='color:#b42318'>· {d['problemas']} com problemas</span>" if d["problemas"] else ""),
                             f"{base}/faturas?periodo={periodo}&filtro=por_conferir", "#9a5a00"))
        texto.append(f"{d['por_conferir']} faturas por conferir ({d['problemas']} com problemas).")
    if d["sem_faturas"]:
        nomes = ", ".join(d["sem_faturas"][:3]) + (f" e mais {len(d['sem_faturas']) - 3}" if len(d["sem_faturas"]) > 3 else "")
        linhas.append(_linha(len(d["sem_faturas"]), f"{'empresa ainda não enviou' if len(d['sem_faturas']) == 1 else 'empresas ainda não enviaram'} faturas "
                             f"<span style='color:#5b6075'>({escape(nomes)})</span>", f"{base}/pedidos?periodo={periodo}"))
        texto.append(f"{len(d['sem_faturas'])} empresas sem faturas: {nomes}.")
    if d["efatura"]:
        linhas.append(_linha(d["efatura"], f"{'fatura está' if d['efatura'] == 1 else 'faturas estão'} no e-Fatura mas não foram enviadas",
                             f"{base}/painel?periodo={periodo}", "#9a5a00"))
        texto.append(f"{d['efatura']} faturas do e-Fatura em falta.")
    semana = (f"Na última semana chegaram <b>{d['recebidos_semana']}</b> documentos"
              + (f", {d['recebidos_portal']} pelo portal dos clientes." if d["recebidos_portal"] else ".")) if d["recebidos_semana"] else \
        "Na última semana não chegaram documentos novos."
    texto.append(semana.replace("<b>", "").replace("</b>", ""))
    primeiro = nome.split()[0] if nome else ""
    assunto = f"{d['mes_txt'].capitalize()}: {d['pct']}% conferido" + (f" · {d['respostas']} respostas de clientes" if d["respostas"] else "")
    html = (
        '<div style="background:#f5f6fa;padding:32px 16px;font-family:system-ui,-apple-system,Segoe UI,sans-serif">'
        '<div style="max-width:560px;margin:0 auto;background:#fff;border:1px solid #e3e6ef;border-radius:20px;padding:32px">'
        '<p style="margin:0 0 24px;font-weight:600;color:#0e1121">Kontiq</p>'
        f'<p style="margin:0 0 4px;color:#5b6075">Olá{(" " + escape(primeiro)) if primeiro else ""}, o resumo da semana de {escape(d["gabinete"])}</p>'
        f'<h1 style="margin:0 0 20px;font-size:28px;font-weight:500;color:#0e1121">{escape(d["mes_txt"].capitalize())}: '
        f'<span style="background:#0e1121;color:#fff;border-radius:999px;padding:0 12px">{d["pct"]}%</span> conferido</h1>'
        f'<table style="width:100%;border-collapse:collapse;font-size:15px">{"".join(linhas)}</table>'
        f'<p style="margin:20px 0 24px;color:#5b6075;font-size:15px">{semana}</p>'
        f'<a href="{base}/painel?periodo={periodo}" style="display:inline-block;background:#4353e8;color:#fff;text-decoration:none;'
        'padding:12px 22px;border-radius:999px;font-weight:500">Abrir o painel</a>'
        f'<p style="margin:28px 0 0;color:#8b90a6;font-size:13px">Recebe este email à segunda-feira. Para deixar de receber, '
        f'desligue o resumo semanal em <a href="{base}/equipa" style="color:#8b90a6">Equipa</a>.</p>'
        '</div></div>'
    )
    return assunto, html, texto


def enviar_a(s: Session, membro: MembroGabinete, u: Utilizador, forcar: bool = False) -> bool:
    d = dados(s, membro.gabinete_id)
    if not forcar and not ha_algo(d):
        return False
    assunto, html, texto = mensagem(d, u.nome)
    enviar_email(u.email, assunto, f"{d['mes_txt'].capitalize()}: {d['pct']}% conferido", texto, html=html)
    membro.resumo_enviado_em = agora()
    return True


def enviar_todos(forcar: bool = False) -> int:
    with sessao_sem_gabinete() as s:
        alvos = s.execute(select(MembroGabinete.id, MembroGabinete.gabinete_id).join(Utilizador, Utilizador.id == MembroGabinete.utilizador_id)
                          .join(Gabinete, Gabinete.id == MembroGabinete.gabinete_id)
                          .where(MembroGabinete.resumo_semanal.is_(True), Utilizador.ativo.is_(True),
                                 Utilizador.email_confirmado_em.is_not(None), Gabinete.estado == "ativo")).all()
    enviados = 0
    for mid, gid in alvos:
        try:
            with sessao_gabinete(gid) as s:
                m = s.get(MembroGabinete, mid)
                if not forcar and m.resumo_enviado_em and agora() - m.resumo_enviado_em < INTERVALO:
                    continue
                enviados += enviar_a(s, m, s.get(Utilizador, m.utilizador_id), forcar)
        except Exception:  # um gabinete com problemas não impede os outros
            log.exception("Falha no resumo semanal do membro %s", mid)
    return enviados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    a = argparse.ArgumentParser(description="Envia o resumo semanal por email às pessoas dos gabinetes.")
    a.add_argument("--forcar", action="store_true", help="envia já, mesmo a quem recebeu há menos de 6 dias")
    n = enviar_todos(a.parse_args().forcar)
    print(f"Resumos enviados: {n}")
