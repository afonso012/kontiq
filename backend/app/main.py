"""API da plataforma e servidor da aplicação web.

- /api/auth, /api/portal, /api/painel: autenticação e áreas com sessão.
- /ferramentas: utilitários sem base de dados.
- /demo e /gabinetes/{id}/…: demonstração SEM autenticação (só fora de produção).
- Tudo o resto: a aplicação web (frontend/dist), se tiver sido construída.
"""
import logging
import mimetypes
import uuid
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select, text

from .api.auth import portal as portal_router
from .api.auth import router as auth_router
from .api.empresas import router as empresas_router
from .api.equipa import router as equipa_router
from .api.subscricao import router as subscricao_router
from .api.exportacoes import router as exportacoes_router
from .api.faturas import router as faturas_router
from .api.portal import router as portal_cliente_router
from .api.painel import router as painel_router
from .auth.servico import ErroAuth
from .core.config import get_settings
from .core.db import engine, sessao_gabinete, sessao_sem_gabinete
from .domain.nif import nif_valido
from .domain.qr_at import QRInvalido, ler_qr
from .domain.validacao import validar
from .models import Empresa, Fatura, Fornecedor, Gabinete, ProblemaFatura

from .core.producao import configurar_registos, verificar_configuracao

configurar_registos()
verificar_configuracao()
_PRODUCAO = get_settings().producao
log = logging.getLogger("faturas.api")

app = FastAPI(
    title="Kontiq",
    version="0.2.0",
    description="API da plataforma. Os endpoints de demonstração não têm autenticação e só existem fora de produção.",
    # Em produção a documentação interativa da API não fica pública.
    docs_url=None if _PRODUCAO else "/docs", redoc_url=None if _PRODUCAO else "/redoc",
    openapi_url=None if _PRODUCAO else "/openapi.json",
)
app.include_router(auth_router)
app.include_router(portal_router)
app.include_router(painel_router)
app.include_router(empresas_router)
app.include_router(faturas_router)
app.include_router(exportacoes_router)
app.include_router(portal_cliente_router)
app.include_router(equipa_router)
app.include_router(subscricao_router)

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "dist"
mimetypes.add_type("application/manifest+json", ".webmanifest")


@app.exception_handler(ErroAuth)
def erro_auth(_: Request, e: ErroAuth) -> JSONResponse:
    return JSONResponse({"codigo": e.codigo, "mensagem": e.mensagem, "campo": e.campo}, status_code=e.status)


@app.middleware("http")
async def cabecalhos_seguranca(request: Request, call_next):
    pedido_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    try:
        resposta = await call_next(request)
    except Exception:
        # Erro inesperado: fica no registo (e no Sentry, se configurado) com o id do pedido;
        # a pessoa vê uma mensagem simples com esse id para o poder indicar ao suporte.
        log.exception("Erro em %s %s (pedido %s)", request.method, request.url.path, pedido_id)
        resposta = JSONResponse({"codigo": "erro_interno", "campo": None,
                                 "mensagem": f"Algo correu mal do nosso lado. Tente outra vez daqui a pouco (ref. {pedido_id})."},
                                status_code=500)
    resposta.headers["X-Request-Id"] = pedido_id
    if _PRODUCAO:
        resposta.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("X-Frame-Options", "DENY")
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    if request.url.path.startswith("/api/"):
        resposta.headers.setdefault("Cache-Control", "no-store")
    return resposta


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

def _so_desenvolvimento() -> None:
    if get_settings().producao:
        raise HTTPException(404)


@app.get("/demo/gabinete", tags=["Demonstração"])
def gabinete_demo() -> dict:
    _so_desenvolvimento()
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
    _so_desenvolvimento()
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
    _so_desenvolvimento()
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


# ---------------- Aplicação web ----------------

@app.get("/{caminho:path}", include_in_schema=False)
def aplicacao_web(caminho: str):
    """Serve o frontend construído; qualquer rota desconhecida devolve o index.html (SPA)."""
    if caminho.startswith(("api/", "docs", "openapi.json", "redoc", "demo/", "gabinetes/", "ferramentas/")):
        raise HTTPException(404)
    if not FRONTEND.exists():
        return RedirectResponse("/docs")
    ficheiro = (FRONTEND / caminho).resolve()
    if caminho and ficheiro.is_file() and FRONTEND in ficheiro.parents:
        cache = "public, max-age=31536000, immutable" if caminho.startswith("assets/") else "no-cache"
        return FileResponse(ficheiro, headers={"Cache-Control": cache})
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})
