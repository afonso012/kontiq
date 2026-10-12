"""Endpoints de autenticação (/api/auth) e do portal do cliente (/api/portal).

A sessão vai num cookie httpOnly (o JavaScript da página não o consegue ler)
com SameSite=Lax, o que impede outros sites de fazer pedidos com ele.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import servico as svc
from ..auth.servico import ErroAuth
from ..core.config import get_settings
from ..core.db import sessao_sem_gabinete
from ..core.seguranca import forca_password
from ..models import Utilizador

COOKIE = "pf_sessao"
T = TypeVar("T")

router = APIRouter(prefix="/api/auth", tags=["Autenticação"])
portal = APIRouter(prefix="/api/portal", tags=["Portal do cliente"])


def executar(fn: Callable[[Session], T]) -> T:
    """Corre `fn` numa transação. Se der ErroAuth, grava na mesma o que já fez
    (tentativas falhadas, contadores dos códigos) e só depois devolve o erro."""
    erro: ErroAuth | None = None
    with sessao_sem_gabinete() as s:
        try:
            resultado = fn(s)
        except ErroAuth as e:
            erro = e
    if erro:
        raise erro
    return resultado


def contexto(request: Request) -> svc.Contexto:
    return svc.Contexto(ip=request.client.host if request.client else None,
                        user_agent=request.headers.get("user-agent"))


def trocar_sessao(request: Request) -> None:
    """Ao entrar com outra conta no mesmo browser, a sessão anterior termina."""
    antigo = request.cookies.get(COOKIE)
    if antigo:
        executar(lambda s: svc.terminar_sessao(s, antigo))


def por_cookie(resp: Response, token: str, persistente: bool, max_dias: int = 30) -> None:
    s = get_settings()
    resp.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=s.producao, path="/",
                    max_age=max_dias * 86400 if persistente else None)


def tirar_cookie(resp: Response) -> None:
    resp.delete_cookie(COOKIE, path="/")


@dataclass
class SessaoAtual:
    sessao_id: str
    utilizador_id: str
    tipo: str
    gabinete_id: str | None
    empresa_id: str | None
    email_confirmado: bool


def sessao_opcional(request: Request) -> SessaoAtual | None:
    token = request.cookies.get(COOKIE)
    if not token:
        return None

    def ler(s: Session):
        sess = svc.sessao_valida(s, token)
        if not sess:
            return None
        u = s.get(Utilizador, sess.utilizador_id)
        if not u or not u.ativo:
            return None
        return SessaoAtual(str(sess.id), str(u.id), sess.tipo, str(sess.gabinete_id) if sess.gabinete_id else None,
                           str(sess.empresa_id) if sess.empresa_id else None, u.email_confirmado_em is not None)
    return executar(ler)


def exigir_sessao(atual: SessaoAtual | None = Depends(sessao_opcional)) -> SessaoAtual:
    if not atual:
        raise ErroAuth(401, "sem_sessao", "A sua sessão terminou. Entre outra vez.")
    return atual


def exigir_gabinete(atual: SessaoAtual = Depends(exigir_sessao)) -> SessaoAtual:
    if atual.tipo != "gabinete":
        raise ErroAuth(403, "so_gabinete", "Esta área é só para o gabinete.")
    if not atual.email_confirmado:
        raise ErroAuth(403, "email_por_confirmar", "Confirme primeiro o seu email.")
    return atual


def exigir_portal(atual: SessaoAtual = Depends(exigir_sessao)) -> SessaoAtual:
    if atual.tipo != "portal":
        raise ErroAuth(403, "so_portal", "Esta área é só para clientes do portal.")
    return atual


def _eu(token: str) -> Callable[[Session], dict]:
    def f(s: Session) -> dict:
        sess = svc.sessao_valida(s, token)
        return svc.descrever(s, sess)
    return f


# ---------------------------------------------------------------- registo

class Conta(BaseModel):
    nome: str = Field(max_length=200)
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class DadosGabinete(BaseModel):
    nome: str = Field(max_length=200)
    nif: str = Field(max_length=20)
    telefone: str | None = Field(default=None, max_length=30)
    programa: str
    dimensao: str


class Registo(Conta):
    gabinete: DadosGabinete


@router.post("/registo/validar-conta")
def validar_conta(corpo: Conta) -> dict:
    """Passo 1 do registo: confirma nome, email e palavra-passe antes de pedir os dados do gabinete."""
    executar(lambda s: svc.validar_conta(s, corpo.nome, corpo.email, corpo.password))
    return {"ok": True}


@router.post("/password/forca")
def forca(corpo: dict) -> dict:
    """Força da palavra-passe (0–4) e o problema, se houver, para o indicador do registo."""
    from ..core.seguranca import problema_password
    pw = str(corpo.get("password", ""))[:200]
    return {"forca": forca_password(pw),
            "problema": problema_password(pw, str(corpo.get("email", "")), str(corpo.get("nome", "")))}


@router.post("/registo", status_code=201)
def registar(corpo: Registo, request: Request, response: Response) -> dict:
    """Cria o gabinete e a conta do dono, envia o código de confirmação e inicia sessão."""
    ctx = contexto(request)
    g = corpo.gabinete

    def f(s: Session):
        _, _, token = svc.registar(s, ctx, nome=corpo.nome, email=corpo.email, password=corpo.password,
                                   nome_gabinete=g.nome, nif=g.nif, telefone=g.telefone,
                                   programa=g.programa, dimensao=g.dimensao)
        return token
    token = executar(f)
    por_cookie(response, token, persistente=False)
    return executar(_eu(token))


class Codigo(BaseModel):
    codigo: str = Field(max_length=12)


@router.post("/email/confirmar")
def confirmar_email(corpo: Codigo, request: Request, atual: SessaoAtual = Depends(exigir_sessao)) -> dict:
    token = request.cookies[COOKIE]

    def f(s: Session):
        svc.confirmar_email(s, s.get(Utilizador, atual.utilizador_id), corpo.codigo)
    executar(f)
    return executar(_eu(token))


@router.post("/email/reenviar")
def reenviar(atual: SessaoAtual = Depends(exigir_sessao)) -> dict:
    executar(lambda s: svc.reenviar_confirmacao(s, s.get(Utilizador, atual.utilizador_id)))
    return {"ok": True}


# ---------------------------------------------------------------- entrar / sair

class Entrar(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    manter: bool = True


@router.post("/entrar")
def entrar(corpo: Entrar, request: Request, response: Response) -> dict:
    ctx = contexto(request)
    token = executar(lambda s: svc.entrar(s, ctx, corpo.email, corpo.password, corpo.manter)[1])
    trocar_sessao(request)
    por_cookie(response, token, persistente=corpo.manter)
    return executar(_eu(token))


@router.post("/sair")
def sair(request: Request, response: Response) -> dict:
    token = request.cookies.get(COOKIE)
    executar(lambda s: svc.terminar_sessao(s, token))
    tirar_cookie(response)
    return {"ok": True}


@router.get("/eu")
def eu(request: Request, atual: SessaoAtual = Depends(exigir_sessao)) -> dict:
    """Quem tem a sessão iniciada."""
    return executar(_eu(request.cookies[COOKIE]))


class PedirReposicao(BaseModel):
    email: str = Field(max_length=254)


@router.post("/password/pedir", status_code=202)
def pedir_reposicao(corpo: PedirReposicao) -> dict:
    """Envia um código para repor a palavra-passe, se o email tiver conta. A resposta é sempre igual."""
    executar(lambda s: svc.pedir_reposicao(s, corpo.email))
    return {"ok": True}


class Repor(BaseModel):
    email: str = Field(max_length=254)
    codigo: str = Field(max_length=12)
    password: str = Field(max_length=200)


@router.post("/password/repor")
def repor(corpo: Repor, request: Request, response: Response) -> dict:
    ctx = contexto(request)
    token = executar(lambda s: svc.repor_password(s, ctx, corpo.email, corpo.codigo, corpo.password)[1])
    por_cookie(response, token, persistente=False)
    return executar(_eu(token))


# ---------------------------------------------------------------- portal

class PedirCodigoPortal(BaseModel):
    canal: Literal["sms", "email"]
    destino: str = Field(max_length=254)


@portal.post("/codigo", status_code=202)
def pedir_codigo_portal(corpo: PedirCodigoPortal) -> dict:
    """Envia um código se o telemóvel/email tiver acesso ao portal. A resposta é sempre igual."""
    executar(lambda s: svc.pedir_codigo_portal(s, corpo.canal, corpo.destino))
    return {"ok": True}


class EntrarPortal(PedirCodigoPortal):
    codigo: str = Field(max_length=12)


@portal.post("/entrar")
def entrar_portal(corpo: EntrarPortal, request: Request, response: Response) -> dict:
    ctx = contexto(request)
    token = executar(lambda s: svc.entrar_portal(s, ctx, corpo.canal, corpo.destino, corpo.codigo)[1])
    trocar_sessao(request)
    por_cookie(response, token, persistente=True, max_dias=60)
    return executar(_eu(token))
