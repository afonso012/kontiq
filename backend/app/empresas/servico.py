"""Empresas-cliente e o painel do gabinete.

Corre sempre numa sessão isolada no gabinete (RLS): as consultas às tabelas de
faturas e empresas só vêem linhas desse gabinete. As tabelas de contas
(utilizadores, acessos ao portal) não têm RLS e são filtradas aqui à mão.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import String, case, cast, func, select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..core import seguranca as seg
from ..core.config import get_settings
from ..core.envio import enviar_email, enviar_sms
from ..domain.nif import nif_valido
from ..models import (
    AcessoPortal, Empresa, Fatura, Gabinete, PedidoDocumentos, ProblemaFatura, RegistoAtividade, Utilizador,
)
from ..models import enums as E

MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]
NOMES_PROBLEMA = {
    "duplicado": "Possível duplicado", "nif_invalido": "NIF inválido", "contas_nao_batem": "Totais não batem",
    "sem_nif": "Sem NIF do fornecedor", "sem_data": "Sem data", "sem_total": "Sem total",
    "iva_estrangeiro": "IVA estrangeiro", "sem_classificacao": "Sem classificação",
}


def agora() -> datetime:
    return datetime.now(timezone.utc)


def mes_por_extenso(d: date) -> str:
    return f"{MESES[d.month - 1]} de {d.year}"


def euros(v: Decimal | float | int) -> str:
    """1234.5 → '1 234,50 €' (formato português)."""
    texto = f"{Decimal(v):,.2f}".replace(",", " ").replace(".", ",")
    return f"{texto} €"


def _registar(s: Session, gabinete_id, utilizador_id, entidade_id, acao: str, dados: dict | None = None) -> None:
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="empresa",
                           entidade_id=entidade_id, acao=acao, dados=dados))


# ---------------------------------------------------------------- painel

def painel(s: Session, gabinete_id: uuid.UUID, mes: date) -> dict:
    mes = mes.replace(day=1)
    # Uma fatura sem QR ainda por preencher não é um "problema": está só por conferir.
    por_preencher = (Fatura.metodo_leitura == "manual") & Fatura.nif_fornecedor.is_(None) & (Fatura.total == 0)
    erros_abertos = (select(ProblemaFatura.fatura_id, func.count().label("n"))
                     .join(Fatura, Fatura.id == ProblemaFatura.fatura_id)
                     .where(ProblemaFatura.resolvido.is_(False), ProblemaFatura.nivel == "erro", ~por_preencher)
                     .group_by(ProblemaFatura.fatura_id).subquery())
    conferida = Fatura.estado.in_(("conferida", "exportada"))
    linhas = s.execute(
        select(Empresa.id, Empresa.nome, Empresa.nif, Empresa.contacto_nome, Empresa.telefone, Empresa.email,
               Empresa.periodicidade_iva, Empresa.criado_em,
               func.count(Fatura.id).label("faturas"),
               func.coalesce(func.sum(Fatura.total), 0).label("total"),
               func.count(case((conferida, 1))).label("conferidas"),
               func.count(case(((Fatura.estado == "por_conferir") & (Fatura.metodo_leitura == "ia"), 1))).label("ia"),
               func.count(case((erros_abertos.c.n > 0, 1))).label("com_erro"),
               func.max(Fatura.criado_em).label("ultima"))
        .outerjoin(Fatura, (Fatura.empresa_id == Empresa.id) & (Fatura.periodo == mes) & Fatura.eliminada_em.is_(None)
                   & (Fatura.estado != "rejeitada"))
        .outerjoin(erros_abertos, erros_abertos.c.fatura_id == Fatura.id)
        .where(Empresa.ativa.is_(True))
        .group_by(Empresa.id)
    ).all()

    com_portal = set(s.scalars(select(AcessoPortal.empresa_id).where(AcessoPortal.gabinete_id == gabinete_id)))
    pedidos = dict(s.execute(
        select(PedidoDocumentos.empresa_id, func.max(PedidoDocumentos.enviado_em))
        .where(PedidoDocumentos.periodo == mes, PedidoDocumentos.estado == "enviado")
        .group_by(PedidoDocumentos.empresa_id)).all())

    ordem = {"bad": 0, "warn": 1, "none": 2, "ok": 3}
    empresas = []
    for l in linhas:
        if l.com_erro:
            estado = "bad"
        elif not l.faturas:
            estado = "none"
        elif l.conferidas < l.faturas:
            estado = "warn"
        else:
            estado = "ok"
        empresas.append({
            "id": str(l.id), "nome": l.nome, "nif": l.nif, "estado": estado,
            "faturas": l.faturas, "total": float(l.total), "total_txt": euros(l.total) if l.faturas else "—",
            "conferidas": l.conferidas, "por_conferir": l.faturas - l.conferidas, "com_erro": l.com_erro,
            "ultima": (l.ultima or l.criado_em).isoformat(),
            "pedido_em": pedidos[l.id].isoformat() if pedidos.get(l.id) else None,
            "portal": l.id in com_portal,
            "contacto": {"nome": l.contacto_nome, "telefone": l.telefone, "email": l.email},
            "periodicidade_iva": l.periodicidade_iva,
        })
    empresas.sort(key=lambda e: (ordem[e["estado"]], e["nome"].lower()))

    # Problemas por resolver, agrupados por empresa e tipo.
    problemas = s.execute(
        select(Empresa.id, Empresa.nome, ProblemaFatura.codigo, func.count().label("n"),
               func.min(Fatura.numero).label("numero"), func.min(cast(Fatura.id, String)).label("fatura_id"))
        .join(Fatura, Fatura.id == ProblemaFatura.fatura_id).join(Empresa, Empresa.id == Fatura.empresa_id)
        .where(ProblemaFatura.resolvido.is_(False), ProblemaFatura.nivel == "erro", Fatura.periodo == mes,
               Fatura.eliminada_em.is_(None), Fatura.estado != "rejeitada", ~por_preencher)
        .group_by(Empresa.id, Empresa.nome, ProblemaFatura.codigo)
        .order_by(func.count().desc())
    ).all()
    atencao = [{
        "nivel": "bad", "empresa_id": str(p.id), "empresa": p.nome, "codigo": p.codigo, "fatura_id": p.fatura_id,
        "titulo": NOMES_PROBLEMA.get(p.codigo, p.codigo.replace("_", " ").capitalize()),
        "detalhe": (f"em {p.n} faturas" if p.n > 1 else (f"de {p.numero}" if p.codigo == "duplicado" and p.numero
                    else "em 1 fatura")),
    } for p in problemas]
    # Faturas que estão no e-Fatura e o cliente ainda não enviou.
    from ..faturas.efatura import resumo_gabinete
    nomes = {e["id"]: e["nome"] for e in empresas}
    atencao += [{"nivel": "warn", "empresa_id": r["empresa_id"], "empresa": nomes.get(r["empresa_id"], ""),
                 "codigo": "efatura_em_falta", "titulo": f"Falta 1 fatura" if r['em_falta'] == 1 else f"Faltam {r['em_falta']} faturas",
                 "detalhe": "que estão no e-Fatura"} for r in resumo_gabinete(s, mes)]
    # Respostas dos clientes às dúvidas do gabinete (de qualquer mês): vêm primeiro.
    respostas = s.execute(
        select(Empresa.id, Empresa.nome, func.count().label("n"), func.min(cast(Fatura.id, String)).label("fatura_id"))
        .join(Fatura, Fatura.empresa_id == Empresa.id)
        .where(Fatura.duvida == "resposta", Fatura.eliminada_em.is_(None))
        .group_by(Empresa.id, Empresa.nome).order_by(Empresa.nome)).all()
    atencao = [{"nivel": "warn", "empresa_id": str(r.id), "empresa": r.nome, "codigo": "cliente_respondeu",
                "fatura_id": r.fatura_id, "titulo": "O cliente respondeu",
                "detalhe": f"a {r.n} dúvidas" if r.n > 1 else "à sua dúvida"} for r in respostas] + atencao
    hoje = date.today()
    # Clientes sem faturas: só a partir do dia 5 do mês seguinte, ou se o mês já passou.
    if mes < hoje.replace(day=1) or hoje.day >= 5:
        for e in empresas:
            if e["estado"] == "none":
                atencao.append({"nivel": "warn", "empresa_id": e["id"], "empresa": e["nome"], "codigo": "sem_faturas",
                                "titulo": f"Sem faturas de {MESES[mes.month - 1]}", "detalhe": "",
                                "pedido": bool(e["pedido_em"])})

    faturas = sum(e["faturas"] for e in empresas)
    conferidas = sum(e["conferidas"] for e in empresas)
    por_codigo: dict[str, int] = {}
    for p in problemas:
        por_codigo[p.codigo] = por_codigo.get(p.codigo, 0) + p.n
    g = s.get(Gabinete, gabinete_id)
    return {
        "periodo": mes.isoformat(), "periodo_txt": mes_por_extenso(mes),
        "gabinete": {"nome": g.nome, "programa": g.programa_contabilidade},
        "totais": {
            "total": float(sum(Decimal(str(e["total"])) for e in empresas)),
            "total_txt": euros(sum(Decimal(str(e["total"])) for e in empresas)),
            "faturas": faturas, "empresas": len(empresas), "conferidas": conferidas,
            "por_conferir": faturas - conferidas, "ia_por_conferir": sum(l.ia for l in linhas),
            "problemas": sum(por_codigo.values()),
            "problemas_txt": " · ".join(f"{n} {NOMES_PROBLEMA.get(c, c).lower()}" for c, n in por_codigo.items()),
            "pct_conferido": round(conferidas / faturas * 100) if faturas else 0,
        },
        "atencao": atencao[:6],
        "empresas": empresas,
        "onboarding": {"empresas": len(empresas) > 0, "portal": len(com_portal) > 0},
    }


# ---------------------------------------------------------------- criar / editar

def _limpar(dados: dict, exigir_contacto: bool) -> dict:
    nif = (dados.get("nif") or "").replace(" ", "")
    nome = (dados.get("nome") or "").strip()
    if not nif_valido(nif):
        raise ErroAuth(422, "nif_invalido", "NIF inválido: confirme os 9 dígitos.", "nif")
    if len(nome) < 2:
        raise ErroAuth(422, "nome_em_falta", "Escreva o nome da empresa.", "nome")
    periodicidade = dados.get("periodicidade_iva") or "trimestral"
    if periodicidade not in E.PERIODICIDADE_IVA:
        raise ErroAuth(422, "periodicidade_invalida", "Escolha a periodicidade do IVA.", "periodicidade_iva")
    tel = (dados.get("telefone") or "").strip()
    email = (dados.get("email") or "").strip()
    tel_n = seg.normalizar_telemovel(tel) if tel else None
    if tel and not tel_n:
        raise ErroAuth(422, "telefone_invalido", "Indique um telemóvel português (9 dígitos).", "telefone")
    email_n = seg.normalizar_email(email) if email else None
    if email and not email_n:
        raise ErroAuth(422, "email_invalido", "Este email não parece válido.", "email")
    contacto = (dados.get("contacto_nome") or "").strip() or None
    if exigir_contacto:
        if not contacto:
            raise ErroAuth(422, "contacto_em_falta", "Escreva o nome de quem envia as faturas.", "contacto_nome")
        if not (tel_n or email_n):
            raise ErroAuth(422, "contacto_sem_meio", "Indique o telemóvel ou o email para enviar o convite.", "telefone")
    return {"nif": nif, "nome": nome[:200], "periodicidade_iva": periodicidade, "telefone": tel_n,
            "email": email_n, "contacto_nome": contacto[:200] if contacto else None}


def criar_empresa(s: Session, gabinete_id, utilizador_id, dados: dict) -> Empresa:
    d = _limpar(dados, exigir_contacto=bool(dados.get("convidar")))
    if s.scalar(select(Empresa.id).where(Empresa.nif == d["nif"])):
        raise ErroAuth(409, "nif_existe", "Esta empresa já está no gabinete.", "nif")
    from ..subscricoes.servico import exigir_vaga_empresa
    exigir_vaga_empresa(s, gabinete_id)
    e = Empresa(gabinete_id=gabinete_id, responsavel_id=utilizador_id, **d)
    s.add(e)
    s.flush()
    _registar(s, gabinete_id, utilizador_id, e.id, "criada", {"nif": e.nif})
    if dados.get("convidar"):
        convidar_portal(s, gabinete_id, utilizador_id, e)
    return e


def editar_empresa(s: Session, gabinete_id, utilizador_id, empresa_id, dados: dict) -> Empresa:
    e = s.get(Empresa, empresa_id)
    if not e or str(e.gabinete_id) != str(gabinete_id):
        raise ErroAuth(404, "nao_encontrada", "Empresa não encontrada.")
    d = _limpar(dados, exigir_contacto=False)
    if d["nif"] != e.nif and s.scalar(select(Empresa.id).where(Empresa.nif == d["nif"], Empresa.id != e.id)):
        raise ErroAuth(409, "nif_existe", "Já existe outra empresa com este NIF.", "nif")
    for k, v in d.items():
        setattr(e, k, v)
    _registar(s, gabinete_id, utilizador_id, e.id, "editada")
    if dados.get("convidar"):
        convidar_portal(s, gabinete_id, utilizador_id, e)
    return e


# ---------------------------------------------------------------- portal e pedidos

def _url_portal() -> str:
    return get_settings().url_publica.rstrip("/") + "/portal"


def convidar_portal(s: Session, gabinete_id, utilizador_id, e: Empresa) -> str:
    """Dá acesso ao portal ao contacto da empresa e envia o convite. Devolve o canal usado."""
    if not e.contacto_nome or not (e.telefone or e.email):
        raise ErroAuth(422, "contacto_sem_meio", "Indique o telemóvel ou o email de quem envia as faturas.", "telefone")
    u = None
    if e.telefone:
        u = s.scalar(select(Utilizador).where(Utilizador.telefone == e.telefone))
    if not u and e.email:
        u = s.scalar(select(Utilizador).where(func.lower(Utilizador.email) == e.email))
    if not u:
        # Quem só tem telemóvel recebe um email técnico que nunca é usado para enviar nada.
        email = e.email or f"{e.telefone.lstrip('+')}@telemovel.local"
        u = Utilizador(nome=e.contacto_nome, email=email, telefone=e.telefone)
        s.add(u)
        s.flush()
    elif e.telefone and not u.telefone:
        u.telefone = e.telefone
    if not s.scalar(select(AcessoPortal.id).where(AcessoPortal.empresa_id == e.id, AcessoPortal.utilizador_id == u.id)):
        s.add(AcessoPortal(gabinete_id=gabinete_id, empresa_id=e.id, utilizador_id=u.id, papel="gestor"))
    g = s.get(Gabinete, gabinete_id)
    primeiro = e.contacto_nome.split()[0]
    if e.telefone:
        enviar_sms(e.telefone, f"Olá {primeiro}. O gabinete {g.nome} convidou-o a enviar as faturas da {e.nome} "
                               f"pelo portal: {_url_portal()} (entra com um código, sem palavra-passe).")
        canal = "sms"
    else:
        enviar_email(e.email, f"{g.nome} convidou-o para o portal de faturas", "Convite para o portal de faturas",
                     [f"Olá {primeiro}, o gabinete {g.nome} convidou-o a enviar as faturas da {e.nome} pelo portal.",
                      f"Entre em {_url_portal()} com este email. Recebe um código, sem palavra-passe."])
        canal = "email"
    _registar(s, gabinete_id, utilizador_id, e.id, "convite_portal", {"canal": canal})
    return canal


def pedir_faturas(s: Session, gabinete_id, utilizador_id, empresa_id, mes: date) -> dict:
    e = s.get(Empresa, empresa_id)
    if not e:
        raise ErroAuth(404, "nao_encontrada", "Empresa não encontrada.")
    if not (e.telefone or e.email):
        raise ErroAuth(422, "contacto_sem_meio", "Esta empresa não tem telemóvel nem email. Edite-a primeiro.")
    mes = mes.replace(day=1)
    ultimo = s.scalar(select(func.max(PedidoDocumentos.enviado_em)).where(
        PedidoDocumentos.empresa_id == e.id, PedidoDocumentos.periodo == mes))
    if ultimo and (agora() - ultimo).total_seconds() < 3600:
        raise ErroAuth(429, "pedido_recente", "Já pediu faturas a esta empresa há menos de uma hora.")
    g = s.get(Gabinete, gabinete_id)
    nome = (e.contacto_nome or "").split()[0] if e.contacto_nome else ""
    texto = (f"Olá{(' ' + nome) if nome else ''}. O gabinete {g.nome} ainda não recebeu as faturas de compras de "
             f"{MESES[mes.month - 1]} da {e.nome}. Pode enviá-las em {_url_portal()}")
    canal = "sms" if e.telefone else "email"
    if canal == "sms":
        enviar_sms(e.telefone, texto)
    else:
        enviar_email(e.email, f"Faturas de {MESES[mes.month - 1]} em falta", "Faturas em falta", [texto])
    s.add(PedidoDocumentos(gabinete_id=gabinete_id, empresa_id=e.id, periodo=mes, mensagem=texto,
                           canal=canal,
                           estado="enviado", criado_por=utilizador_id, enviado_em=agora()))
    _registar(s, gabinete_id, utilizador_id, e.id, "pedido_faturas", {"canal": canal, "periodo": mes.isoformat()})
    return {"canal": canal}
