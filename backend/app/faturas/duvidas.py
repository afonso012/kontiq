"""Dúvidas sobre uma fatura entre o gabinete e o cliente.

O gabinete escreve na conferência ("Perguntar ao cliente"); o cliente recebe um
SMS ou email com o link do portal e responde lá. O estado fica na fatura:
  None        sem dúvida em aberto
  "pergunta"  o gabinete espera resposta do cliente
  "resposta"  o cliente respondeu e o gabinete ainda não fechou a dúvida
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..core.envio import enviar_email, enviar_sms, escolher_sms
from ..empresas.servico import _url_portal, euros
from ..models import Comentario, Documento, Empresa, Fatura, Fornecedor, Gabinete, RegistoAtividade, Utilizador

MAX_TEXTO = 1000


def _texto(texto: str) -> str:
    t = " ".join((texto or "").split())
    if not t:
        raise ErroAuth(422, "texto_vazio", "Escreva a mensagem.", "texto")
    if len(t) > MAX_TEXTO:
        raise ErroAuth(422, "texto_longo", f"Use no máximo {MAX_TEXTO} caracteres.", "texto")
    return t


def _fatura(s: Session, fatura_id, empresa_id=None) -> Fatura:
    f = s.get(Fatura, fatura_id)
    if not f or f.eliminada_em or (empresa_id and str(f.empresa_id) != str(empresa_id)):
        raise ErroAuth(404, "nao_encontrada", "Fatura não encontrada.")
    return f


def conversa(s: Session, fatura_id) -> list[dict]:
    linhas = s.execute(select(Comentario, Utilizador.nome).outerjoin(Utilizador, Utilizador.id == Comentario.autor_id)
                       .where(Comentario.fatura_id == fatura_id)
                       .order_by(Comentario.criado_em, Comentario.id)).all()
    return [{"id": str(c.id), "lado": c.lado, "autor": nome, "texto": c.texto, "em": c.criado_em.isoformat()}
            for c, nome in linhas]


def _descricao(s: Session, f: Fatura) -> str:
    forn = s.get(Fornecedor, f.fornecedor_id) if f.fornecedor_id else None
    partes = [f"a fatura {f.numero}" if f.numero else "uma fatura"]
    if forn and not forn.nome.startswith("Fornecedor "):
        partes.append(f"do fornecedor {forn.nome}")
    if f.total:
        partes.append(f"({euros(f.total)})")
    return " ".join(partes)


def escrever_gabinete(s: Session, gabinete_id, utilizador_id, fatura_id, texto: str) -> dict:
    """Mensagem do gabinete. Avisa o cliente quando abre (ou reabre) a dúvida."""
    t = _texto(texto)
    f = _fatura(s, fatura_id)
    e = s.get(Empresa, f.empresa_id)
    avisar = f.duvida != "pergunta"
    if avisar and not (e.telefone or e.email):
        raise ErroAuth(422, "contacto_sem_meio", "Esta empresa não tem telemóvel nem email para avisar o cliente. Edite-a primeiro.")
    s.add(Comentario(gabinete_id=gabinete_id, fatura_id=f.id, autor_id=utilizador_id, lado="gabinete", texto=t))
    f.duvida = "pergunta"
    canal = None
    if avisar:
        g = s.get(Gabinete, gabinete_id)
        nome = (e.contacto_nome or "").split()[0] if e.contacto_nome else ""
        msg = (f"Olá{(' ' + nome) if nome else ''}. O gabinete {g.nome} tem uma dúvida sobre {_descricao(s, f)} "
               f"da empresa {e.nome}: \"{t[:160]}{'…' if len(t) > 160 else ''}\" Responda em {_url_portal()}")
        canal = "sms" if e.telefone else "email"
        if canal == "sms":
            # A pergunta fica no portal; o SMS só avisa (curto, numa parte).
            numero = f" {f.numero}" if f.numero else ""
            valor = f" ({euros(f.total)})" if f.total else ""
            ola = f"Olá{(' ' + nome) if nome else ''}. "
            enviar_sms(e.telefone, escolher_sms(
                f"{ola}{g.nome} tem uma pergunta sobre a fatura{numero}{valor} da empresa {e.nome}. Responda em {_url_portal()}",
                f"{ola}{g.nome} tem uma pergunta sobre a fatura{numero}{valor}. Responda em {_url_portal()}",
                f"{g.nome} tem uma pergunta sobre a fatura{numero}{valor}. Responda em {_url_portal()}",
                f"{g.nome} tem uma pergunta sobre a fatura{numero}. Responda em {_url_portal()}"))
        else:
            enviar_email(e.email, f"Dúvida sobre {_descricao(s, f)}", "O seu gabinete tem uma dúvida", [msg])
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="fatura", entidade_id=f.id,
                           acao="duvida_enviada", dados={"canal": canal}))
    s.flush()
    return {"duvida": f.duvida, "mensagens": conversa(s, f.id), "avisado": canal}


def resolver(s: Session, gabinete_id, utilizador_id, fatura_id) -> dict:
    f = _fatura(s, fatura_id)
    f.duvida = None
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="fatura", entidade_id=f.id,
                           acao="duvida_resolvida", dados={}))
    return {"duvida": None, "mensagens": conversa(s, f.id)}


# ---------------------------------------------------------------- portal do cliente

def do_cliente(s: Session, empresa_id) -> list[dict]:
    """Dúvidas em aberto desta empresa, a mais antiga primeiro."""
    linhas = s.execute(select(Fatura, Fornecedor.nome, Documento.nome_original)
                       .outerjoin(Fornecedor, Fornecedor.id == Fatura.fornecedor_id)
                       .outerjoin(Documento, Documento.id == Fatura.documento_id)
                       .where(Fatura.empresa_id == empresa_id, Fatura.duvida.is_not(None), Fatura.eliminada_em.is_(None))
                       .order_by(Fatura.criado_em)).all()
    return [{
        "fatura_id": str(f.id), "estado": f.duvida, "numero": f.numero,
        "fornecedor": forn if forn and not forn.startswith("Fornecedor ") else None,
        "data": f.data_emissao.isoformat() if f.data_emissao else None,
        "total": euros(f.total) if f.total else None,
        "documento": {"id": str(f.documento_id), "nome": nome} if f.documento_id else None,
        "mensagens": conversa(s, f.id),
    } for f, forn, nome in linhas]


def responder_cliente(s: Session, gabinete_id, empresa_id, utilizador_id, fatura_id, texto: str) -> dict:
    t = _texto(texto)
    f = _fatura(s, fatura_id, empresa_id)
    if not f.duvida:
        raise ErroAuth(409, "sem_duvida", "O gabinete já fechou esta dúvida.")
    s.add(Comentario(gabinete_id=gabinete_id, fatura_id=f.id, autor_id=utilizador_id, lado="cliente", texto=t))
    f.duvida = "resposta"
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="fatura", entidade_id=f.id,
                           acao="duvida_respondida", dados={}))
    s.flush()
    return {"estado": f.duvida, "mensagens": conversa(s, f.id)}
