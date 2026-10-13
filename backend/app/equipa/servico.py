"""Equipa do gabinete: membros, papéis e convites.

Papéis: dono (quem registou; um por gabinete), admin (gere a equipa) e
colaborador (trabalha nas faturas). Só dono e admin convidam e mudam papéis.
Tabelas de contas (sem RLS): tudo é filtrado pelo gabinete da sessão.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..auth import servico as auth
from ..auth.servico import ErroAuth
from ..core import seguranca as seg
from ..core.config import get_settings
from ..core.envio import enviar_email
from ..models import Convite, Gabinete, MembroGabinete, RegistoAtividade, Utilizador

VALIDADE = timedelta(days=7)
PAPEIS_CONVITE = ("admin", "colaborador")
NOMES = {"dono": "Dono", "admin": "Administrador", "colaborador": "Colaborador"}


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _papel(s: Session, gabinete_id, utilizador_id) -> str | None:
    return s.scalar(select(MembroGabinete.papel).where(MembroGabinete.gabinete_id == gabinete_id,
                                                       MembroGabinete.utilizador_id == utilizador_id))


def _exigir_gestor(s: Session, gabinete_id, utilizador_id) -> str:
    p = _papel(s, gabinete_id, utilizador_id)
    if p not in ("dono", "admin"):
        raise ErroAuth(403, "sem_permissao", "Só o dono ou um administrador pode gerir a equipa.")
    return p


def _registar(s: Session, gabinete_id, utilizador_id, acao: str, dados: dict) -> None:
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="equipa", acao=acao, dados=dados))


def listar(s: Session, gabinete_id, utilizador_id) -> dict:
    membros = s.execute(select(MembroGabinete, Utilizador).join(Utilizador, Utilizador.id == MembroGabinete.utilizador_id)
                        .where(MembroGabinete.gabinete_id == gabinete_id).order_by(MembroGabinete.criado_em)).all()
    convites = s.scalars(select(Convite).where(Convite.gabinete_id == gabinete_id, Convite.empresa_id.is_(None),
                                               Convite.aceite_em.is_(None), Convite.expira_em > agora())
                         .order_by(Convite.criado_em.desc())).all()
    eu = _papel(s, gabinete_id, utilizador_id)
    return {
        "eu": {"id": str(utilizador_id), "papel": eu, "pode_gerir": eu in ("dono", "admin")},
        "membros": [{"id": str(m.id), "utilizador_id": str(u.id), "nome": u.nome, "email": u.email, "papel": m.papel,
                     "papel_nome": NOMES[m.papel], "ultimo_login": u.ultimo_login.isoformat() if u.ultimo_login else None,
                     "ativo": u.ativo} for m, u in membros],
        "convites": [{"id": str(c.id), "email": c.email, "papel": c.papel, "papel_nome": NOMES.get(c.papel, c.papel),
                      "criado_em": c.criado_em.isoformat(), "expira_em": c.expira_em.isoformat()} for c in convites],
    }


def _enviar(s: Session, c: Convite, token: str, quem: Utilizador) -> None:
    g = s.get(Gabinete, c.gabinete_id)
    url = f"{get_settings().url_publica.rstrip('/')}/convite/{token}"
    enviar_email(c.email, f"Convite de {quem.nome} para o gabinete {g.nome}", "Convite para a equipa",
                 [f"{quem.nome} enviou-lhe um convite para trabalhar nas faturas dos clientes do gabinete {g.nome}.",
                  f"Para aceitar, abra este endereço: {url}",
                  "O convite é válido durante 7 dias. Se não estava à espera dele, ignore este email."])


def convidar(s: Session, gabinete_id, utilizador_id, email: str, papel: str) -> dict:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    email_n = seg.normalizar_email(email)
    if not email_n:
        raise ErroAuth(422, "email_invalido", "Este email não parece válido.", "email")
    if papel not in PAPEIS_CONVITE:
        raise ErroAuth(422, "papel_invalido", "Escolha administrador ou colaborador.", "papel")
    ja = s.scalar(select(MembroGabinete.id).join(Utilizador, Utilizador.id == MembroGabinete.utilizador_id)
                  .where(MembroGabinete.gabinete_id == gabinete_id, func.lower(Utilizador.email) == email_n))
    if ja:
        raise ErroAuth(409, "ja_membro", "Esta pessoa já faz parte da equipa.", "email")
    from ..subscricoes.servico import exigir_vaga_pessoa
    pendente = s.scalar(select(Convite.id).where(Convite.gabinete_id == gabinete_id, Convite.empresa_id.is_(None),
                                                 func.lower(Convite.email) == email_n, Convite.aceite_em.is_(None),
                                                 Convite.expira_em > agora()))
    if not pendente:  # um convite novo para o mesmo email só substitui o anterior
        exigir_vaga_pessoa(s, gabinete_id)
    # Um convite novo substitui um pendente para o mesmo email.
    for antigo in s.scalars(select(Convite).where(Convite.gabinete_id == gabinete_id, Convite.empresa_id.is_(None),
                                                  func.lower(Convite.email) == email_n, Convite.aceite_em.is_(None))):
        antigo.expira_em = agora()
    token = secrets.token_urlsafe(32)
    c = Convite(gabinete_id=gabinete_id, email=email_n, papel=papel, token_hash=_hash(token), convidado_por=utilizador_id,
                expira_em=agora() + VALIDADE)
    s.add(c)
    s.flush()
    _enviar(s, c, token, s.get(Utilizador, utilizador_id))
    _registar(s, gabinete_id, utilizador_id, "convite_enviado", {"email": email_n, "papel": papel})
    return {"id": str(c.id), "email": email_n}


def reenviar(s: Session, gabinete_id, utilizador_id, convite_id) -> None:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    c = s.get(Convite, convite_id)
    if not c or str(c.gabinete_id) != str(gabinete_id) or c.aceite_em:
        raise ErroAuth(404, "nao_encontrado", "Convite não encontrado.")
    token = secrets.token_urlsafe(32)
    c.token_hash, c.expira_em = _hash(token), agora() + VALIDADE
    _enviar(s, c, token, s.get(Utilizador, utilizador_id))


def cancelar(s: Session, gabinete_id, utilizador_id, convite_id) -> None:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    c = s.get(Convite, convite_id)
    if not c or str(c.gabinete_id) != str(gabinete_id) or c.aceite_em:
        raise ErroAuth(404, "nao_encontrado", "Convite não encontrado.")
    c.expira_em = agora()
    _registar(s, gabinete_id, utilizador_id, "convite_cancelado", {"email": c.email})


def mudar_papel(s: Session, gabinete_id, utilizador_id, membro_id, papel: str) -> None:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    m = s.get(MembroGabinete, membro_id)
    if not m or str(m.gabinete_id) != str(gabinete_id):
        raise ErroAuth(404, "nao_encontrado", "Membro não encontrado.")
    if m.papel == "dono":
        raise ErroAuth(409, "dono", "O papel do dono não pode ser alterado.")
    if papel not in PAPEIS_CONVITE:
        raise ErroAuth(422, "papel_invalido", "Escolha administrador ou colaborador.")
    m.papel = papel
    _registar(s, gabinete_id, utilizador_id, "papel_alterado", {"membro": str(m.utilizador_id), "papel": papel})


def remover(s: Session, gabinete_id, utilizador_id, membro_id) -> None:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    m = s.get(MembroGabinete, membro_id)
    if not m or str(m.gabinete_id) != str(gabinete_id):
        raise ErroAuth(404, "nao_encontrado", "Membro não encontrado.")
    if m.papel == "dono":
        raise ErroAuth(409, "dono", "O dono do gabinete não pode ser removido.")
    if str(m.utilizador_id) == str(utilizador_id):
        raise ErroAuth(409, "a_si_proprio", "Não se pode remover a si próprio.")
    uid = m.utilizador_id
    s.delete(m)
    # As sessões dessa pessoa neste gabinete terminam já.
    from ..models import Sessao
    for sess in s.scalars(select(Sessao).where(Sessao.utilizador_id == uid, Sessao.gabinete_id == gabinete_id,
                                               Sessao.terminada_em.is_(None))):
        sess.terminada_em = agora()
    _registar(s, gabinete_id, utilizador_id, "membro_removido", {"membro": str(uid)})


# ---------------------------------------------------------------- aceitar (sem sessão)

def _convite_valido(s: Session, token: str) -> Convite:
    c = s.scalar(select(Convite).where(Convite.token_hash == _hash(token or "")))
    if not c or c.empresa_id is not None:
        raise ErroAuth(404, "convite_invalido", "Este convite não existe. Peça um novo a quem lhe enviou o convite.")
    if c.aceite_em:
        raise ErroAuth(410, "convite_usado", "Este convite já foi aceite. Entre com o seu email e palavra-passe.")
    if c.expira_em <= agora():
        raise ErroAuth(410, "convite_expirado", "Este convite expirou. Peça um novo a quem lhe enviou o convite.")
    return c


def ver_convite(s: Session, token: str) -> dict:
    c = _convite_valido(s, token)
    g, quem = s.get(Gabinete, c.gabinete_id), s.get(Utilizador, c.convidado_por) if c.convidado_por else None
    existe = s.scalar(select(Utilizador.id).where(func.lower(Utilizador.email) == c.email.lower())) is not None
    return {"gabinete": g.nome, "email": c.email, "papel": NOMES.get(c.papel, c.papel),
            "convidado_por": quem.nome if quem else None, "conta_existe": existe}


def aceitar(s: Session, ctx: auth.Contexto, token: str, nome: str | None, password: str) -> str:
    """Cria a conta (ou usa a existente, confirmando a palavra-passe) e junta-a ao gabinete. Devolve o token de sessão."""
    c = _convite_valido(s, token)
    u = s.scalar(select(Utilizador).where(func.lower(Utilizador.email) == c.email.lower()))
    if u:
        if not seg.verificar_password(u.password_hash, password or ""):
            raise ErroAuth(401, "credenciais", "Palavra-passe errada para esta conta.", "password")
    else:
        nome = (nome or "").strip()
        if len(nome) < 2:
            raise ErroAuth(422, "nome_em_falta", "Escreva o seu nome.", "nome")
        if (p := seg.problema_password(password or "", c.email, nome)):
            raise ErroAuth(422, "password_fraca", p, "password")
        # O email foi confirmado ao abrir o link que lá chegou.
        u = Utilizador(nome=nome, email=c.email, password_hash=seg.hash_password(password), email_confirmado_em=agora())
        s.add(u)
        s.flush()
    if not s.scalar(select(MembroGabinete.id).where(MembroGabinete.gabinete_id == c.gabinete_id,
                                                    MembroGabinete.utilizador_id == u.id)):
        s.add(MembroGabinete(gabinete_id=c.gabinete_id, utilizador_id=u.id, papel=c.papel))
    c.aceite_em = agora()
    # O registo de atividade está isolado por gabinete (RLS): fixa o gabinete do convite.
    s.execute(text("SELECT set_config('app.gabinete_id', :g, true)"), {"g": str(c.gabinete_id)})
    _registar(s, c.gabinete_id, u.id, "convite_aceite", {"email": c.email})
    return auth.criar_sessao(s, u, ctx, tipo="gabinete", gabinete_id=c.gabinete_id)
