"""API do Faturas em Dia.

Fase 0: endpoints de demonstração SEM autenticação, só para uso local.
O gabinete vai no URL; na fase 1 passa a vir do login.
"""
import uuid
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select, text

from .core.db import engine, sessao_gabinete, sessao_sem_gabinete
from .domain.nif import nif_valido
from .domain.qr_at import QRInvalido, ler_qr
from .domain.validacao import validar
from .models import Empresa, Fatura, Fornecedor, Gabinete, ProblemaFatura

app = FastAPI(
    title="Faturas em Dia",
    version="0.1.0",
    description="API da plataforma. **Fase 0 — demonstração local, sem autenticação.**",
)


@app.get("/", include_in_schema=False)
def inicio():
    return RedirectResponse("/docs")


@app.get("/saude", tags=["Sistema"])
def saude() -> dict:
    """Confirma que a API está viva e consegue falar com a base de dados."""
    with engine.connect() as c:
        tabelas = c.execute(text(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")).scalar()
    return {"estado": "ok", "tabelas": tabelas}


# ---------------- Ferramentas (sem base de dados) ----------------

class TextoQR(BaseModel):
    texto: str

    model_config = {"json_schema_extra": {"examples": [{"texto": (
        "A:514873205*B:999999990*C:PT*D:FT*E:N*F:20261009*G:FT 2026/0457*H:JFR2M8KQ-457*"
        "I1:PT*I7:77.90*I8:17.92*N:17.92*O:95.82*Q:aB3x*R:2153")}]}}


@app.post("/ferramentas/ler-qr", tags=["Ferramentas"])
def ler_codigo_qr(corpo: TextoQR) -> dict:
    """Lê o texto de um código QR de uma fatura portuguesa e valida-o."""
    try:
        q = ler_qr(corpo.texto)
    except QRInvalido as e:
        raise HTTPException(422, str(e))
    problemas = validar(pais_fornecedor="PT", nif_fornecedor=q.nif_emitente, base_total=q.base_total,
                        iva_total=q.iva_total, total=q.total, data_emissao=q.data_emissao,
                        tipo_documento=q.tipo_documento, tratamento_iva="por_definir", conta_codigo=None)
    return {
        "nif_fornecedor": q.nif_emitente, "nif_valido": nif_valido(q.nif_emitente),
        "tipo_documento": q.tipo_documento, "numero": q.numero, "atcud": q.atcud,
        "data": q.data_emissao, "base": q.base_total, "iva": q.iva_total, "total": q.total,
        "linhas_iva": [{"espaco_fiscal": l.espaco_fiscal, "tipo_taxa": l.tipo_taxa, "taxa_%": l.taxa,
                        "base": l.base, "iva": l.iva} for l in q.linhas_iva],
        "problemas": [p.__dict__ for p in problemas if p.codigo != "sem_classificacao"],
    }


@app.get("/ferramentas/validar-nif/{nif}", tags=["Ferramentas"])
def validar_nif(nif: str) -> dict:
    """Diz se um NIF português é válido (dígito de controlo)."""
    return {"nif": nif, "valido": nif_valido(nif)}


# ---------------- Gabinete (demonstração) ----------------

@app.get("/demo/gabinete", tags=["Demonstração"])
def gabinete_demo() -> dict:
    """Devolve o id do gabinete de demonstração (criado pelo `python -m app.demo`)."""
    with sessao_sem_gabinete() as s:
        g = s.scalar(select(Gabinete).where(Gabinete.nif == "502877642"))
        if not g:
            raise HTTPException(404, "Ainda não há dados de demonstração. Corra: python -m app.demo")
        return {"gabinete_id": g.id, "nome": g.nome}


@app.get("/gabinetes/{gabinete_id}/empresas", tags=["Gabinete"])
def estado_clientes(gabinete_id: uuid.UUID, periodo: date = Query(date(2026, 10, 1), description="Qualquer dia do mês")) -> list[dict]:
    """Estado de cada empresa-cliente no mês: faturas, total, problemas e estado.

    Só devolve dados do gabinete indicado: o isolamento é feito pelo PostgreSQL (RLS).
    """
    mes = periodo.replace(day=1)
    with sessao_gabinete(gabinete_id) as s:
        abertos = (select(ProblemaFatura.fatura_id, func.count().label("n"))
                   .where(ProblemaFatura.resolvido.is_(False), ProblemaFatura.nivel == "erro")
                   .group_by(ProblemaFatura.fatura_id).subquery())
        linhas = s.execute(
            select(Empresa.id, Empresa.nome, Empresa.nif,
                   func.count(Fatura.id).label("faturas"),
                   func.coalesce(func.sum(Fatura.total), 0).label("total"),
                   func.count(case((Fatura.estado == "por_conferir", 1))).label("por_conferir"),
                   func.coalesce(func.sum(abertos.c.n), 0).label("problemas"))
            .outerjoin(Fatura, (Fatura.empresa_id == Empresa.id) & (Fatura.periodo == mes) & Fatura.eliminada_em.is_(None))
            .outerjoin(abertos, abertos.c.fatura_id == Fatura.id)
            .group_by(Empresa.id).order_by(Empresa.nome)
        ).all()
    out = []
    for l in linhas:
        estado = ("Sem faturas" if not l.faturas else "Com problemas" if l.problemas
                  else "Por conferir" if l.por_conferir else "Completa")
        out.append({"empresa_id": l.id, "nome": l.nome, "nif": l.nif, "estado": estado,
                    "faturas": l.faturas, "total": l.total, "por_conferir": l.por_conferir, "problemas": l.problemas})
    return out


@app.get("/gabinetes/{gabinete_id}/empresas/{empresa_id}/faturas", tags=["Gabinete"])
def faturas_empresa(gabinete_id: uuid.UUID, empresa_id: uuid.UUID,
                    periodo: date = Query(date(2026, 10, 1), description="Qualquer dia do mês")) -> list[dict]:
    """Faturas de uma empresa num mês, com fornecedor, classificação e problemas."""
    mes = periodo.replace(day=1)
    with sessao_gabinete(gabinete_id) as s:
        faturas = s.scalars(
            select(Fatura).where(Fatura.empresa_id == empresa_id, Fatura.periodo == mes, Fatura.eliminada_em.is_(None))
            .order_by(Fatura.data_emissao)
        ).all()
        nomes = dict(s.execute(select(Fornecedor.id, Fornecedor.nome)).all())
        return [{
            "data": f.data_emissao, "fornecedor": nomes.get(f.fornecedor_id), "nif": f.nif_fornecedor,
            "numero": f.numero, "atcud": f.atcud, "base": f.base_total, "iva": f.iva_total, "total": f.total,
            "conta_snc": f.conta_codigo, "tratamento_iva": f.tratamento_iva, "leitura": f.metodo_leitura,
            "estado": f.estado, "notas": f.notas,
            "problemas": [{"nivel": p.nivel, "mensagem": p.mensagem} for p in f.problemas if not p.resolvido],
        } for f in faturas]
