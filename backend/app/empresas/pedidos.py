"""Pedidos aos clientes: faturas em falta e dúvidas, num só sítio.

- em_falta: empresas sem faturas no mês (e se já se pediu)
- pedidos: histórico dos pedidos de faturas enviados (SMS ou email) e se o cliente já enviou depois
- duvidas: faturas com uma dúvida em aberto
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..models import Comentario, Documento, Empresa, Fatura, Fornecedor, PedidoDocumentos, Utilizador
from .servico import MESES, euros, painel, pedir_faturas


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _txt(mes: date) -> str:
    return f"{MESES[mes.month - 1]} de {mes.year}"


def listar(s: Session, gabinete_id, mes: date) -> dict:
    mes = mes.replace(day=1)
    p = painel(s, gabinete_id, mes)
    em_falta = [{
        "id": e["id"], "nome": e["nome"], "nif": e["nif"], "contacto": e["contacto"], "portal": e["portal"],
        "pedido_em": e["pedido_em"],
        "meio": "sms" if e["contacto"]["telefone"] else "email" if e["contacto"]["email"] else None,
    } for e in p["empresas"] if e["estado"] == "none"]

    desde = agora() - timedelta(days=90)
    linhas = s.execute(select(PedidoDocumentos, Empresa.nome, Utilizador.nome)
                       .join(Empresa, Empresa.id == PedidoDocumentos.empresa_id)
                       .outerjoin(Utilizador, Utilizador.id == PedidoDocumentos.criado_por)
                       .where(PedidoDocumentos.enviado_em >= desde)
                       .order_by(PedidoDocumentos.enviado_em.desc()).limit(100)).all()
    # Último documento recebido por empresa, para saber se o cliente respondeu ao pedido.
    ultimos = dict(s.execute(select(Documento.empresa_id, func.max(Documento.criado_em)).group_by(Documento.empresa_id)).all())
    pedidos = []
    for ped, empresa, quem in linhas:
        recebeu = ultimos.get(ped.empresa_id)
        pedidos.append({
            "id": str(ped.id), "empresa": {"id": str(ped.empresa_id), "nome": empresa}, "periodo": ped.periodo.isoformat(),
            "periodo_txt": _txt(ped.periodo), "canal": ped.canal, "enviado_em": ped.enviado_em.isoformat(), "quem": quem,
            "respondido": bool(recebeu and recebeu > ped.enviado_em),
        })

    abertas = s.execute(select(Fatura, Empresa.nome, Fornecedor.nome)
                        .join(Empresa, Empresa.id == Fatura.empresa_id)
                        .outerjoin(Fornecedor, Fornecedor.id == Fatura.fornecedor_id)
                        .where(Fatura.duvida.is_not(None), Fatura.eliminada_em.is_(None))
                        .order_by(Fatura.duvida.desc(), Fatura.criado_em)).all()
    ultimas = {}
    if abertas:
        for c in s.scalars(select(Comentario).where(Comentario.fatura_id.in_([f.id for f, _, _ in abertas]))
                           .order_by(Comentario.criado_em)):
            ultimas[c.fatura_id] = c
    duvidas = [{
        "fatura_id": str(f.id), "estado": f.duvida, "empresa": {"id": str(f.empresa_id), "nome": empresa},
        "fornecedor": forn if forn and not forn.startswith("Fornecedor ") else None, "numero": f.numero,
        "total": euros(f.total) if f.total else None,
        "ultima": {"texto": ultimas[f.id].texto, "lado": ultimas[f.id].lado, "em": ultimas[f.id].criado_em.isoformat()}
        if f.id in ultimas else None,
    } for f, empresa, forn in abertas]
    duvidas.sort(key=lambda d: (d["estado"] != "resposta", d["ultima"]["em"] if d["ultima"] else ""))

    return {
        "periodo": mes.isoformat(), "periodo_txt": _txt(mes),
        "em_falta": em_falta, "pedidos": pedidos, "duvidas": duvidas,
        "contagens": {"em_falta": len(em_falta), "respostas": sum(1 for d in duvidas if d["estado"] == "resposta"),
                      "a_espera": sum(1 for d in duvidas if d["estado"] == "pergunta")},
    }


def pedir_a_todas(s: Session, gabinete_id, utilizador_id, mes: date) -> dict:
    """Pede as faturas do mês a todas as empresas que ainda não enviaram nada."""
    mes = mes.replace(day=1)
    from ..subscricoes.servico import exigir_ativa
    exigir_ativa(s, gabinete_id)
    alvo = listar(s, gabinete_id, mes)["em_falta"]
    if not alvo:
        raise ErroAuth(409, "nada_a_pedir", "Todas as empresas já enviaram faturas deste mês.")
    enviados, ignoradas = [], []
    for e in alvo:
        if not e["meio"]:
            ignoradas.append({"nome": e["nome"], "motivo": "sem telemóvel nem email"})
            continue
        try:
            r = pedir_faturas(s, gabinete_id, utilizador_id, uuid.UUID(e["id"]), mes)
            enviados.append({"nome": e["nome"], "canal": r["canal"]})
        except ErroAuth as erro:
            ignoradas.append({"nome": e["nome"], "motivo": "já pedido há menos de uma hora" if erro.codigo == "pedido_recente" else erro.mensagem})
    return {"enviados": enviados, "ignoradas": ignoradas}
