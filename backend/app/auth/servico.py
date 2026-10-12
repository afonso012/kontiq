"""Regras da autenticação: registo, entrada, códigos e sessões.

Tudo aqui trabalha sobre as tabelas de contas (sem RLS). As funções recebem
uma sessão SQLAlchemy aberta e levantam `ErroAuth` com uma mensagem pronta a
mostrar ao utilizador.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..core import seguranca as seg
from ..core.envio import enviar_email, enviar_sms
from ..domain.nif import nif_valido
from ..models import (
    AcessoPortal, CodigoVerificacao, Empresa, Gabinete, MembroGabinete, Sessao, TentativaLogin,
    Utilizador,
)
from ..models import enums as E

# Limites
VALIDADE_CODIGO = timedelta(minutes=15)
TENTATIVAS_POR_CODIGO = 5
CODIGOS_POR_HORA = 5
ESPERA_REENVIO = timedelta(seconds=60)
JANELA_LOGIN = timedelta(minutes=15)
FALHAS_POR_CONTA = 8
FALHAS_POR_IP = 40
SESSAO_CURTA = timedelta(hours=12)
SESSAO_LONGA = timedelta(days=30)
SESSAO_PORTAL = timedelta(days=60)


class ErroAuth(Exception):
    def __init__(self, status: int, codigo: str, mensagem: str, campo: str | None = None):
        super().__init__(mensagem)
        self.status, self.codigo, self.mensagem, self.campo = status, codigo, mensagem, campo


def agora() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Contexto:
    ip: str | None = None
    user_agent: str | None = None


# ---------------------------------------------------------------- tentativas

def _falhas_recentes(s: Session, chave: str) -> int:
    return s.scalar(select(func.count()).select_from(TentativaLogin).where(
        TentativaLogin.chave == chave, TentativaLogin.sucesso.is_(False),
        TentativaLogin.criado_em > agora() - JANELA_LOGIN)) or 0


def _travar_se_preciso(s: Session, chave_conta: str, ctx: Contexto) -> None:
    if _falhas_recentes(s, chave_conta) >= FALHAS_POR_CONTA or (
            ctx.ip and _falhas_recentes(s, f"ip:{ctx.ip}") >= FALHAS_POR_IP):
        raise ErroAuth(429, "demasiadas_tentativas",
                       "Demasiadas tentativas falhadas. Espere 15 minutos e tente outra vez.")


def _registar_tentativa(s: Session, chave_conta: str, ctx: Contexto, sucesso: bool) -> None:
    s.add(TentativaLogin(chave=chave_conta, sucesso=sucesso))
    if ctx.ip and not sucesso:
        s.add(TentativaLogin(chave=f"ip:{ctx.ip}", sucesso=False))


# ---------------------------------------------------------------- sessões

def criar_sessao(s: Session, u: Utilizador, ctx: Contexto, *, tipo: str, gabinete_id: uuid.UUID,
                 empresa_id: uuid.UUID | None = None, duracao: timedelta = SESSAO_CURTA) -> str:
    token, token_hash = seg.novo_token()
    s.add(Sessao(token_hash=token_hash, utilizador_id=u.id, tipo=tipo, gabinete_id=gabinete_id,
                 empresa_id=empresa_id, expira_em=agora() + duracao,
                 user_agent=(ctx.user_agent or "")[:300] or None, ip=ctx.ip))
    u.ultimo_login = agora()
    return token


def sessao_valida(s: Session, token: str | None) -> Sessao | None:
    if not token:
        return None
    sessao = s.scalar(select(Sessao).where(Sessao.token_hash == seg.hash_token(token)))
    if not sessao or sessao.terminada_em or sessao.expira_em <= agora():
        return None
    if agora() - sessao.ultimo_uso > timedelta(minutes=5):
        sessao.ultimo_uso = agora()
    return sessao


def terminar_sessao(s: Session, token: str | None) -> None:
    if token:
        s.execute(update(Sessao).where(Sessao.token_hash == seg.hash_token(token), Sessao.terminada_em.is_(None))
                  .values(terminada_em=agora()))


def terminar_todas(s: Session, utilizador_id: uuid.UUID) -> None:
    s.execute(update(Sessao).where(Sessao.utilizador_id == utilizador_id, Sessao.terminada_em.is_(None))
              .values(terminada_em=agora()))


# ---------------------------------------------------------------- códigos

def _emitir_codigo(s: Session, u: Utilizador, finalidade: str, canal: str, destino: str) -> str | None:
    """Cria e envia um código. Devolve None (sem enviar) se o limite por hora foi atingido."""
    recentes = s.scalars(select(CodigoVerificacao).where(
        CodigoVerificacao.destino == destino, CodigoVerificacao.finalidade == finalidade,
        CodigoVerificacao.criado_em > agora() - timedelta(hours=1)).order_by(CodigoVerificacao.criado_em.desc())).all()
    if len(recentes) >= CODIGOS_POR_HORA:
        return None
    # Um código novo invalida os anteriores da mesma finalidade.
    for c in recentes:
        if not c.usado_em:
            c.usado_em = agora()
    codigo, codigo_hash = seg.novo_codigo()
    s.add(CodigoVerificacao(utilizador_id=u.id, finalidade=finalidade, canal=canal, destino=destino,
                            codigo_hash=codigo_hash, expira_em=agora() + VALIDADE_CODIGO))
    _enviar_codigo(finalidade, canal, destino, codigo, u.nome)
    return codigo


def _enviar_codigo(finalidade: str, canal: str, destino: str, codigo: str, nome: str) -> None:
    primeiro = nome.split()[0] if nome else ""
    if canal == "sms":
        enviar_sms(destino, f"O seu código de entrada no portal de faturas é {codigo}. Válido durante 15 minutos.")
        return
    textos = {
        "confirmar_email": ("Confirme o seu email", "Confirme o seu email",
                            [f"Olá {primeiro}, introduza este código para confirmar o email e abrir o painel."]),
        "repor_password": ("Repor a palavra-passe", "Repor a palavra-passe",
                           [f"Olá {primeiro}, recebemos um pedido para repor a sua palavra-passe.",
                            "Se não foi você, ignore este email: a palavra-passe atual continua a funcionar."]),
        "entrar_portal": ("Código de entrada no portal", "O seu código de entrada",
                          [f"Olá {primeiro}, use este código para entrar no portal de faturas."]),
    }
    assunto, titulo, pars = textos[finalidade]
    enviar_email(destino, f"{codigo} · {assunto}", titulo, pars + ["O código é válido durante 15 minutos."], codigo)


def _consumir_codigo(s: Session, destino: str, finalidade: str, codigo: str) -> CodigoVerificacao:
    """Valida o código mais recente desse destino. Erros genéricos para não revelar nada."""
    erro = ErroAuth(400, "codigo_invalido", "Código errado ou expirado. Verifique ou peça um novo.", "codigo")
    c = s.scalar(select(CodigoVerificacao).where(
        CodigoVerificacao.destino == destino, CodigoVerificacao.finalidade == finalidade,
        CodigoVerificacao.usado_em.is_(None), CodigoVerificacao.expira_em > agora(),
    ).order_by(CodigoVerificacao.criado_em.desc()).limit(1).with_for_update())
    if not c:
        raise erro
    if c.tentativas >= TENTATIVAS_POR_CODIGO:
        c.usado_em = agora()
        raise ErroAuth(429, "demasiadas_tentativas", "Demasiadas tentativas. Peça um código novo.", "codigo")
    if not seg.codigo_confere(codigo, c.codigo_hash):
        c.tentativas += 1
        if c.tentativas >= TENTATIVAS_POR_CODIGO:
            c.usado_em = agora()
        raise erro
    c.usado_em = agora()
    return c


# ---------------------------------------------------------------- registo

def _utilizador_por_email(s: Session, email: str) -> Utilizador | None:
    return s.scalar(select(Utilizador).where(func.lower(Utilizador.email) == email))


def validar_conta(s: Session, nome: str, email: str, password: str) -> str:
    """Passo 1 do registo. Devolve o email normalizado."""
    nome = (nome or "").strip()
    if len(nome) < 2:
        raise ErroAuth(422, "nome_em_falta", "Escreva o seu nome.", "nome")
    email_n = seg.normalizar_email(email)
    if not email_n:
        raise ErroAuth(422, "email_invalido", "Este email não parece válido.", "email")
    if (p := seg.problema_password(password, email_n, nome)):
        raise ErroAuth(422, "password_fraca", p, "password")
    if _utilizador_por_email(s, email_n):
        raise ErroAuth(409, "email_existe", "Já existe uma conta com este email. Entre ou reponha a palavra-passe.", "email")
    return email_n


PROGRAMAS = dict(zip(("TOConline", "Primavera", "PHC", "Sage", "Outro"), E.PROGRAMAS_CONTABILIDADE))


def registar(s: Session, ctx: Contexto, *, nome: str, email: str, password: str, nome_gabinete: str,
             nif: str, telefone: str | None, programa: str, dimensao: str) -> tuple[Utilizador, Gabinete, str]:
    email_n = validar_conta(s, nome, email, password)
    nome_gabinete = (nome_gabinete or "").strip()
    nif = (nif or "").replace(" ", "")
    if len(nome_gabinete) < 2:
        raise ErroAuth(422, "nome_gabinete_em_falta", "Escreva o nome do gabinete.", "nome_gabinete")
    if not nif_valido(nif):
        raise ErroAuth(422, "nif_invalido", "NIF inválido: confirme os 9 dígitos.", "nif")
    if s.scalar(select(Gabinete.id).where(Gabinete.nif == nif)):
        raise ErroAuth(409, "nif_existe", "Este gabinete já está registado. Peça um convite a quem o registou.", "nif")
    tel = None
    if telefone and telefone.strip():
        tel = seg.normalizar_telemovel(telefone)
        if not tel:
            raise ErroAuth(422, "telefone_invalido", "Indique um telemóvel português (9 dígitos).", "telefone")
    if programa not in E.PROGRAMAS_CONTABILIDADE:
        raise ErroAuth(422, "programa_invalido", "Escolha o programa de contabilidade.", "programa")
    if dimensao not in E.DIMENSOES_GABINETE:
        raise ErroAuth(422, "dimensao_invalida", "Escolha quantas empresas acompanha.", "dimensao")

    g = Gabinete(nome=nome_gabinete, nif=nif, email=email_n, telefone=tel,
                 programa_contabilidade=programa, dimensao=dimensao)
    u = Utilizador(nome=nome.strip(), email=email_n, password_hash=seg.hash_password(password))
    s.add_all([g, u]); s.flush()
    s.add(MembroGabinete(gabinete_id=g.id, utilizador_id=u.id, papel="dono"))
    _emitir_codigo(s, u, "confirmar_email", "email", email_n)
    token = criar_sessao(s, u, ctx, tipo="gabinete", gabinete_id=g.id)
    return u, g, token


def confirmar_email(s: Session, u: Utilizador, codigo: str) -> None:
    if u.email_confirmado_em:
        return
    _consumir_codigo(s, u.email.lower(), "confirmar_email", codigo)
    u.email_confirmado_em = agora()


def reenviar_confirmacao(s: Session, u: Utilizador) -> None:
    if u.email_confirmado_em:
        return
    ultimo = s.scalar(select(func.max(CodigoVerificacao.criado_em)).where(
        CodigoVerificacao.destino == u.email.lower(), CodigoVerificacao.finalidade == "confirmar_email"))
    if ultimo and agora() - ultimo < ESPERA_REENVIO:
        falta = int((ESPERA_REENVIO - (agora() - ultimo)).total_seconds()) + 1
        raise ErroAuth(429, "espere", f"Espere {falta} segundos para pedir outro código.")
    if not _emitir_codigo(s, u, "confirmar_email", "email", u.email.lower()):
        raise ErroAuth(429, "demasiados_codigos", "Já pedimos vários códigos. Tente daqui a uma hora.")


# ---------------------------------------------------------------- entrar

def entrar(s: Session, ctx: Contexto, email: str, password: str, manter: bool) -> tuple[Utilizador, str]:
    email_n = seg.normalizar_email(email) or (email or "").strip().lower()
    chave = f"email:{email_n}"
    _travar_se_preciso(s, chave, ctx)
    u = _utilizador_por_email(s, email_n)
    ok = seg.verificar_password(u.password_hash if u else None, password or "")
    membro = s.scalar(select(MembroGabinete).where(MembroGabinete.utilizador_id == u.id)
                      .order_by(MembroGabinete.criado_em).limit(1)) if (ok and u) else None
    if not (ok and u and u.ativo and membro):
        _registar_tentativa(s, chave, ctx, False)
        raise ErroAuth(401, "credenciais", "Email ou palavra-passe errados.")
    _registar_tentativa(s, chave, ctx, True)
    token = criar_sessao(s, u, ctx, tipo="gabinete", gabinete_id=membro.gabinete_id,
                         duracao=SESSAO_LONGA if manter else SESSAO_CURTA)
    return u, token


def pedir_reposicao(s: Session, email: str) -> None:
    """Sempre sucesso visível: não revela se o email tem conta."""
    email_n = seg.normalizar_email(email)
    u = _utilizador_por_email(s, email_n) if email_n else None
    if u and u.ativo and u.password_hash:
        _emitir_codigo(s, u, "repor_password", "email", email_n)


def repor_password(s: Session, ctx: Contexto, email: str, codigo: str, password: str) -> tuple[Utilizador, str]:
    email_n = seg.normalizar_email(email) or ""
    u = _utilizador_por_email(s, email_n)
    if not u:
        raise ErroAuth(400, "codigo_invalido", "Código errado ou expirado. Verifique ou peça um novo.", "codigo")
    _consumir_codigo(s, email_n, "repor_password", codigo)
    if (p := seg.problema_password(password, email_n, u.nome)):
        raise ErroAuth(422, "password_fraca", p, "password")
    u.password_hash = seg.hash_password(password)
    u.email_confirmado_em = u.email_confirmado_em or agora()
    terminar_todas(s, u.id)
    membro = s.scalar(select(MembroGabinete).where(MembroGabinete.utilizador_id == u.id).limit(1))
    if not membro:
        raise ErroAuth(403, "sem_gabinete", "Esta conta não pertence a nenhum gabinete.")
    return u, criar_sessao(s, u, ctx, tipo="gabinete", gabinete_id=membro.gabinete_id)


# ---------------------------------------------------------------- portal do cliente

def _destino_portal(canal: str, destino: str) -> str | None:
    if canal == "sms":
        return seg.normalizar_telemovel(destino)
    if canal == "email":
        return seg.normalizar_email(destino)
    return None


def _utilizador_portal(s: Session, canal: str, destino: str) -> tuple[Utilizador, AcessoPortal] | None:
    col = Utilizador.telefone if canal == "sms" else func.lower(Utilizador.email)
    linha = s.execute(select(Utilizador, AcessoPortal).join(AcessoPortal, AcessoPortal.utilizador_id == Utilizador.id)
                      .where(col == destino, Utilizador.ativo.is_(True))
                      .order_by(AcessoPortal.criado_em).limit(1)).first()
    return (linha[0], linha[1]) if linha else None


def pedir_codigo_portal(s: Session, canal: str, destino: str) -> None:
    d = _destino_portal(canal, destino)
    if not d:
        campo = "telefone" if canal == "sms" else "email"
        msg = "Indique um telemóvel português (9 dígitos)." if canal == "sms" else "Este email não parece válido."
        raise ErroAuth(422, "destino_invalido", msg, campo)
    achado = _utilizador_portal(s, canal, d)
    if achado:
        _emitir_codigo(s, achado[0], "entrar_portal", canal, d)


def entrar_portal(s: Session, ctx: Contexto, canal: str, destino: str, codigo: str) -> tuple[Utilizador, str]:
    d = _destino_portal(canal, destino) or ""
    chave = f"portal:{d}"
    _travar_se_preciso(s, chave, ctx)
    achado = _utilizador_portal(s, canal, d)
    try:
        if not achado:
            raise ErroAuth(400, "codigo_invalido", "Código errado ou expirado. Verifique ou peça um novo.", "codigo")
        _consumir_codigo(s, d, "entrar_portal", codigo)
    except ErroAuth:
        _registar_tentativa(s, chave, ctx, False)
        raise
    u, acesso = achado
    _registar_tentativa(s, chave, ctx, True)
    if canal == "email" and not u.email_confirmado_em:
        u.email_confirmado_em = agora()
    token = criar_sessao(s, u, ctx, tipo="portal", gabinete_id=acesso.gabinete_id,
                         empresa_id=acesso.empresa_id, duracao=SESSAO_PORTAL)
    return u, token


# ---------------------------------------------------------------- quem sou eu

def descrever(s: Session, sessao: Sessao) -> dict:
    u = s.get(Utilizador, sessao.utilizador_id)
    g = s.get(Gabinete, sessao.gabinete_id) if sessao.gabinete_id else None
    out = {
        "tipo": sessao.tipo,
        "utilizador": {"id": str(u.id), "nome": u.nome, "email": u.email,
                       "email_confirmado": u.email_confirmado_em is not None},
        "gabinete": {"id": str(g.id), "nome": g.nome} if g else None,
    }
    if sessao.tipo == "gabinete":
        m = s.scalar(select(MembroGabinete).where(MembroGabinete.utilizador_id == u.id,
                                                  MembroGabinete.gabinete_id == sessao.gabinete_id))
        out["papel"] = m.papel if m else None
    return out
