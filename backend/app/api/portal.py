"""Portal do cliente (/api/portal/inicio, /api/portal/documentos).

O cliente só vê a própria empresa: a sessão do portal traz o gabinete e a
empresa, e as consultas correm isoladas nesse gabinete (RLS) e filtradas pela empresa.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select

from ..auth.servico import ErroAuth
from ..core.db import sessao_gabinete
from ..empresas.servico import MESES, euros
from ..faturas import servico as fsvc
from ..models import Documento, Empresa, Fatura, Fornecedor, Gabinete, PedidoDocumentos, Utilizador
from .auth import SessaoAtual, exigir_portal

router = APIRouter(prefix="/api/portal", tags=["Portal do cliente"])

ESTADOS = {"por_conferir": "recebida", "conferida": "tratada", "exportada": "tratada", "rejeitada": "rejeitada"}


@router.get("/inicio")
def inicio(atual: SessaoAtual = Depends(exigir_portal)) -> dict:
    """O que o cliente vê ao entrar: o mês, o que já enviou e o que o gabinete pediu."""
    hoje = date.today()
    mes = hoje.replace(day=1)
    with sessao_gabinete(atual.gabinete_id) as s:
        e, g, u = s.get(Empresa, atual.empresa_id), s.get(Gabinete, atual.gabinete_id), s.get(Utilizador, atual.utilizador_id)
        desde = hoje - timedelta(days=45)
        linhas = s.execute(
            select(Documento, Fatura, Fornecedor.nome)
            .outerjoin(Fatura, (Fatura.documento_id == Documento.id) & Fatura.eliminada_em.is_(None))
            .outerjoin(Fornecedor, Fornecedor.id == Fatura.fornecedor_id)
            .where(Documento.empresa_id == e.id, Documento.criado_em >= desde)
            .order_by(Documento.criado_em.desc()).limit(60)).all()
        enviados = [{
            "id": str(d.id), "nome": d.nome_original, "enviado_em": d.criado_em.isoformat(), "canal": d.canal,
            "por_mim": str(d.enviado_por) == atual.utilizador_id,
            "estado": ESTADOS.get(f.estado, "recebida") if f else "recebida",
            "fornecedor": forn if forn and not forn.startswith("Fornecedor ") else None,
            "total": euros(f.total) if f and f.total else None,
            "data": f.data_emissao.isoformat() if f and f.data_emissao else None,
        } for d, f, forn in linhas]
        este_mes = sum(1 for d, f, _ in linhas if d.criado_em.date() >= mes)
        pedido = s.scalar(select(PedidoDocumentos).where(
            PedidoDocumentos.empresa_id == e.id, PedidoDocumentos.estado == "enviado",
            PedidoDocumentos.periodo >= (mes - timedelta(days=1)).replace(day=1))
            .order_by(PedidoDocumentos.enviado_em.desc()).limit(1))
        pedido_info = None
        if pedido:
            depois = any(d.criado_em > pedido.enviado_em for d, _, _ in linhas) if pedido.enviado_em else False
            if not depois:
                pedido_info = {"periodo_txt": f"{MESES[pedido.periodo.month - 1]} de {pedido.periodo.year}",
                               "enviado_em": pedido.enviado_em.isoformat() if pedido.enviado_em else None}
        return {
            "empresa": {"nome": e.nome, "nif": e.nif}, "gabinete": {"nome": g.nome},
            "utilizador": {"nome": u.nome}, "mes_txt": f"{MESES[mes.month - 1]} de {mes.year}",
            "enviados_mes": este_mes, "enviados": enviados, "pedido": pedido_info,
        }


@router.post("/documentos")
async def enviar(ficheiros: list[UploadFile] = File(...), atual: SessaoAtual = Depends(exigir_portal)) -> dict:
    """O cliente envia fotografias ou PDFs das faturas. Entram no gabinete por conferir."""
    if len(ficheiros) > 10:
        raise ErroAuth(422, "demasiados_ficheiros", "Envie no máximo 10 ficheiros de cada vez.")
    lidos = [(f.filename or "fatura", await f.read(fsvc.MAX_BYTES + 1)) for f in ficheiros]
    with sessao_gabinete(atual.gabinete_id) as s:
        res = fsvc.carregar(s, atual.gabinete_id, atual.utilizador_id, atual.empresa_id, lidos,
                            date.today().replace(day=1), canal="portal")
    # Ao cliente só interessa se ficou recebida; a leitura é assunto do gabinete.
    return {"resultados": [{"nome": r.nome, "ok": r.estado in ("lida", "ia", "manual"), "repetido": r.estado == "repetido",
                            "mensagem": ("Recebida." if r.estado in ("lida", "ia", "manual")
                                         else "Já tinha enviado este ficheiro." if r.estado == "repetido" else r.mensagem),
                            "fornecedor": r.fornecedor if r.fornecedor and not r.fornecedor.startswith("Fornecedor ") else None,
                            "total": r.total} for r in res]}
