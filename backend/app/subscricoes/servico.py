"""Subscrições do gabinete: planos, período de teste, limites e pagamentos.

Planos por número de empresas-cliente e de pessoas na equipa. Todos os gabinetes
começam num período de teste com os limites do plano Gabinete. Depois:

  teste      dentro do período de teste
  expirada   o teste acabou sem pagamento          → só consulta e exporta
  ativa      pago até `proxima_renovacao`
  em_atraso  passou a renovação e ainda não pagou  → funciona durante GRACA
  suspensa   em atraso há mais de GRACA            → só consulta e exporta
  cancelada  cancelou e o período pago acabou     → só consulta e exporta

"expirada" e "suspensa" são calculados; na base de dados o estado é um dos
quatro de ESTADOS_SUBSCRICAO.

Pagamentos: `PAGAMENTOS_MODO=simulado` cria uma página de pagamento de teste
dentro da própria aplicação (nunca em produção). Um fornecedor real (Stripe,
Easypay, ifthenpay…) entra em `iniciar_pagamento` e num webhook que chama `_aplicar`.
"""
from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..core.config import get_settings
from ..models import Convite, Empresa, MembroGabinete, PagamentoSubscricao, RegistoAtividade, Subscricao, Utilizador

IVA = 0.23
TESTE_DIAS = 30
GRACA = timedelta(days=7)
PLANO_TESTE = "gabinete"

# Preços sem IVA, em cêntimos. pessoas=None: sem limite.
PLANOS: dict[str, dict] = {
    "arranque": {"nome": "Arranque", "empresas": 10, "pessoas": 2, "mensal": 2900,
                 "para": "Contabilistas independentes a começar.",
                 "inclui": ["Até 10 empresas-cliente", "2 pessoas na equipa", "Leitura do QR da AT", "Portal do cliente",
                            "Exportação Excel e CSV"]},
    "gabinete": {"nome": "Gabinete", "empresas": 40, "pessoas": 5, "mensal": 7900, "destaque": True,
                 "para": "O gabinete típico, com uma pequena equipa.",
                 "inclui": ["Até 40 empresas-cliente", "5 pessoas na equipa", "Tudo do Arranque",
                            "Leitura automática de faturas sem QR", "Dúvidas com o cliente por SMS"]},
    "pro": {"nome": "Pro", "empresas": 100, "pessoas": None, "mensal": 14900,
            "para": "Gabinetes com muitos clientes.",
            "inclui": ["Até 100 empresas-cliente", "Pessoas ilimitadas", "Tudo do Gabinete",
                       "Formatos dos programas de contabilidade (em breve)", "Apoio prioritário"]},
}
CICLOS = ("mensal", "anual")  # anual = 10 meses (2 meses grátis)
NOMES_ESTADO = {"teste": "Período de teste", "expirada": "Teste terminado", "ativa": "Ativa",
                "em_atraso": "Pagamento em atraso", "suspensa": "Suspensa", "cancelada": "Cancelada"}
ESTADOS_QUE_TRABALHAM = ("teste", "ativa", "em_atraso")


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _mais_meses(d: datetime, n: int) -> datetime:
    m = d.month - 1 + n
    ano, mes = d.year + m // 12, m % 12 + 1
    return d.replace(year=ano, month=mes, day=min(d.day, calendar.monthrange(ano, mes)[1]))


def preco(plano: str, ciclo: str) -> tuple[int, int]:
    """(valor sem IVA, IVA) em cêntimos para um período."""
    base = PLANOS[plano]["mensal"] * (10 if ciclo == "anual" else 1)
    return base, round(base * IVA)


def euros(cents: int) -> str:
    v = f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",")
    return (v[:-3] if v.endswith(",00") else v) + " €"


# ---------------------------------------------------------------- estado

def criar_teste(s: Session, gabinete_id) -> Subscricao:
    p = PLANOS[PLANO_TESTE]
    sub = Subscricao(gabinete_id=gabinete_id, plano=PLANO_TESTE, estado="teste", limite_empresas=p["empresas"],
                     preco_mensal_cents=p["mensal"], fim_teste=agora() + timedelta(days=TESTE_DIAS))
    s.add(sub)
    s.flush()
    return sub


def obter(s: Session, gabinete_id) -> Subscricao:
    """A subscrição do gabinete (cria o teste se ainda não existir) com o estado guardado atualizado."""
    sub = s.scalar(select(Subscricao).where(Subscricao.gabinete_id == gabinete_id))
    if not sub:
        return criar_teste(s, gabinete_id)
    if sub.estado in ("ativa", "em_atraso") and sub.proxima_renovacao and sub.proxima_renovacao <= agora():
        sub.estado = "cancelada" if sub.cancelar_no_fim else "em_atraso"
    return sub


def estado(sub: Subscricao) -> str:
    if sub.estado == "teste":
        return "teste" if sub.fim_teste and sub.fim_teste > agora() else "expirada"
    if sub.estado == "em_atraso" and sub.proxima_renovacao and sub.proxima_renovacao + GRACA <= agora():
        return "suspensa"
    return sub.estado


def limites(sub: Subscricao) -> dict:
    p = PLANOS[sub.plano]
    return {"empresas": sub.limite_empresas, "pessoas": p["pessoas"]}


def _dias(ate: datetime | None) -> int | None:
    if not ate:
        return None
    return max(0, (ate - agora() + timedelta(hours=23, minutes=59)).days)


def resumo(s: Session, gabinete_id) -> dict:
    sub = obter(s, gabinete_id)
    e = estado(sub)
    dias = _dias(sub.fim_teste) if e == "teste" else _dias(sub.proxima_renovacao + GRACA) if e == "em_atraso" else None
    aviso = None
    if e == "teste" and dias is not None and dias <= 7:
        aviso = f"O período de teste termina {'hoje' if dias == 0 else f'daqui a {dias} dias' if dias > 1 else 'amanhã'}. Escolha um plano para continuar."
    elif e == "expirada":
        aviso = "O período de teste terminou. Pode consultar e exportar; para carregar faturas, escolha um plano."
    elif e == "em_atraso":
        aviso = f"O pagamento da subscrição está em atraso. Regularize nos próximos {dias} dias para não perder o acesso."
    elif e == "suspensa":
        aviso = "A subscrição está suspensa por falta de pagamento. Pode consultar e exportar."
    elif e == "cancelada":
        aviso = "A subscrição foi cancelada. Pode consultar e exportar; para voltar a trabalhar, escolha um plano."
    elif e == "ativa" and sub.cancelar_no_fim:
        aviso = f"A subscrição termina a {sub.proxima_renovacao:%d/%m/%Y} e não será renovada."
    return {"plano": sub.plano, "plano_nome": PLANOS[sub.plano]["nome"], "estado": e, "estado_nome": NOMES_ESTADO[e],
            "dias": dias, "pode_trabalhar": e in ESTADOS_QUE_TRABALHAM, "aviso": aviso}


def _uso(s: Session, gabinete_id) -> dict:
    empresas = s.scalar(select(func.count()).select_from(Empresa).where(Empresa.gabinete_id == gabinete_id))
    pessoas = s.scalar(select(func.count()).select_from(MembroGabinete).where(MembroGabinete.gabinete_id == gabinete_id))
    convites = s.scalar(select(func.count()).select_from(Convite).where(
        Convite.gabinete_id == gabinete_id, Convite.empresa_id.is_(None), Convite.aceite_em.is_(None),
        Convite.expira_em > agora()))
    return {"empresas": empresas or 0, "pessoas": pessoas or 0, "convites": convites or 0}


# ---------------------------------------------------------------- limites (chamados pelas outras áreas)

def exigir_ativa(s: Session, gabinete_id) -> Subscricao:
    sub = obter(s, gabinete_id)
    e = estado(sub)
    if e not in ESTADOS_QUE_TRABALHAM:
        msg = {"expirada": "O período de teste terminou.", "suspensa": "A subscrição está suspensa por falta de pagamento.",
               "cancelada": "A subscrição foi cancelada."}[e]
        raise ErroAuth(402, "subscricao_inativa", f"{msg} Escolha um plano em Subscrição para continuar.")
    return sub


def exigir_vaga_empresa(s: Session, gabinete_id) -> None:
    sub = exigir_ativa(s, gabinete_id)
    if _uso(s, gabinete_id)["empresas"] >= sub.limite_empresas:
        raise ErroAuth(402, "limite_empresas",
                       f"O plano {PLANOS[sub.plano]['nome']} inclui até {sub.limite_empresas} empresas. Mude de plano em Subscrição para adicionar mais.")


def exigir_vaga_pessoa(s: Session, gabinete_id) -> None:
    sub = exigir_ativa(s, gabinete_id)
    limite = PLANOS[sub.plano]["pessoas"]
    u = _uso(s, gabinete_id)
    if limite is not None and u["pessoas"] + u["convites"] >= limite:
        raise ErroAuth(402, "limite_pessoas",
                       f"O plano {PLANOS[sub.plano]['nome']} inclui {limite} pessoas (contando convites pendentes). Mude de plano em Subscrição para convidar mais.")


# ---------------------------------------------------------------- página da subscrição

def _gestor(s: Session, gabinete_id, utilizador_id) -> bool:
    papel = s.scalar(select(MembroGabinete.papel).where(MembroGabinete.gabinete_id == gabinete_id,
                                                        MembroGabinete.utilizador_id == utilizador_id))
    return papel in ("dono", "admin")


def _exigir_gestor(s: Session, gabinete_id, utilizador_id) -> None:
    if not _gestor(s, gabinete_id, utilizador_id):
        raise ErroAuth(403, "sem_permissao", "Só o dono ou um administrador pode gerir a subscrição.")


def _pagamento_json(p: PagamentoSubscricao, quem: str | None = None) -> dict:
    return {"id": str(p.id), "plano": p.plano, "plano_nome": PLANOS[p.plano]["nome"], "ciclo": p.ciclo,
            "valor": euros(p.valor_cents), "iva": euros(p.iva_cents), "total": euros(p.valor_cents + p.iva_cents),
            "estado": p.estado, "fornecedor": p.fornecedor, "criado_em": p.criado_em.isoformat(),
            "pago_em": p.pago_em.isoformat() if p.pago_em else None,
            "periodo_fim": p.periodo_fim.isoformat() if p.periodo_fim else None, "quem": quem}


def detalhe(s: Session, gabinete_id, utilizador_id) -> dict:
    sub = obter(s, gabinete_id)
    pagamentos = s.execute(select(PagamentoSubscricao, Utilizador.nome)
                           .outerjoin(Utilizador, Utilizador.id == PagamentoSubscricao.criado_por)
                           .where(PagamentoSubscricao.gabinete_id == gabinete_id, PagamentoSubscricao.estado != "anulado")
                           .order_by(PagamentoSubscricao.criado_em.desc()).limit(24)).all()
    uso = _uso(s, gabinete_id)
    planos = []
    for pid, p in PLANOS.items():
        m, a = preco(pid, "mensal"), preco(pid, "anual")
        cabe = uso["empresas"] <= p["empresas"] and (p["pessoas"] is None or uso["pessoas"] <= p["pessoas"])
        planos.append({"id": pid, "nome": p["nome"], "para": p["para"], "inclui": p["inclui"], "destaque": bool(p.get("destaque")),
                       "empresas": p["empresas"], "pessoas": p["pessoas"],
                       "mensal": euros(m[0]), "anual": euros(a[0]), "anual_por_mes": euros(round(a[0] / 12)),
                       "cabe": cabe})
    return {
        **resumo(s, gabinete_id),
        "ciclo": sub.ciclo, "cancelar_no_fim": sub.cancelar_no_fim,
        "fim_teste": sub.fim_teste.isoformat() if sub.fim_teste else None,
        "proxima_renovacao": sub.proxima_renovacao.isoformat() if sub.proxima_renovacao else None,
        "preco": euros(sub.preco_mensal_cents * (10 if sub.ciclo == "anual" else 1)),
        "uso": uso, "limites": limites(sub), "planos": planos,
        "pagamentos": [_pagamento_json(p, nome) for p, nome in pagamentos],
        "pode_gerir": _gestor(s, gabinete_id, utilizador_id),
        "modo_pagamento": get_settings().pagamentos_modo,
    }


# ---------------------------------------------------------------- pagar, cancelar

def iniciar_pagamento(s: Session, gabinete_id, utilizador_id, plano: str, ciclo: str) -> dict:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    if plano not in PLANOS:
        raise ErroAuth(422, "plano_invalido", "Escolha um dos planos.")
    if ciclo not in CICLOS:
        raise ErroAuth(422, "ciclo_invalido", "Escolha pagamento mensal ou anual.")
    modo = get_settings().pagamentos_modo
    if modo == "desligado":
        raise ErroAuth(503, "pagamentos_desligados", "Os pagamentos ainda não estão disponíveis. Fale connosco.")
    p, uso = PLANOS[plano], _uso(s, gabinete_id)
    if uso["empresas"] > p["empresas"]:
        raise ErroAuth(409, "excede_empresas", f"Tem {uso['empresas']} empresas e o plano {p['nome']} inclui até {p['empresas']}. Remova empresas ou escolha outro plano.")
    if p["pessoas"] is not None and uso["pessoas"] > p["pessoas"]:
        raise ErroAuth(409, "excede_pessoas", f"A equipa tem {uso['pessoas']} pessoas e o plano {p['nome']} inclui {p['pessoas']}. Remova pessoas ou escolha outro plano.")
    sub = obter(s, gabinete_id)
    if estado(sub) == "ativa" and sub.plano == plano and sub.ciclo == ciclo and not sub.cancelar_no_fim:
        raise ErroAuth(409, "ja_neste_plano", "Já está neste plano.")
    # Pedidos anteriores por concluir deixam de valer.
    for antigo in s.scalars(select(PagamentoSubscricao).where(PagamentoSubscricao.gabinete_id == gabinete_id,
                                                              PagamentoSubscricao.estado == "pendente")):
        antigo.estado = "anulado"
    valor, iva = preco(plano, ciclo)
    pag = PagamentoSubscricao(gabinete_id=gabinete_id, plano=plano, ciclo=ciclo, valor_cents=valor, iva_cents=iva,
                              estado="pendente", fornecedor=modo, criado_por=utilizador_id)
    s.add(pag)
    s.flush()
    return {"pagamento": str(pag.id), "url": f"/subscricao/pagamento/{pag.id}"}


def _pagamento(s: Session, gabinete_id, pagamento_id) -> PagamentoSubscricao:
    p = s.get(PagamentoSubscricao, pagamento_id)
    if not p or str(p.gabinete_id) != str(gabinete_id):
        raise ErroAuth(404, "nao_encontrado", "Pagamento não encontrado.")
    return p


def ver_pagamento(s: Session, gabinete_id, pagamento_id) -> dict:
    p = _pagamento(s, gabinete_id, pagamento_id)
    return {**_pagamento_json(p), "modo": get_settings().pagamentos_modo}


def _aplicar(s: Session, p: PagamentoSubscricao, utilizador_id) -> None:
    """Pagamento confirmado: muda o plano e abre um período novo a partir de hoje."""
    sub = obter(s, p.gabinete_id)
    inicio = agora()
    fim = _mais_meses(inicio, 12 if p.ciclo == "anual" else 1)
    plano = PLANOS[p.plano]
    sub.plano, sub.ciclo, sub.estado = p.plano, p.ciclo, "ativa"
    sub.limite_empresas, sub.preco_mensal_cents = plano["empresas"], plano["mensal"]
    sub.proxima_renovacao, sub.cancelar_no_fim = fim, False
    sub.fornecedor_pagamento, sub.referencia_externa = p.fornecedor, str(p.id)
    p.estado, p.pago_em, p.periodo_inicio, p.periodo_fim = "pago", inicio, inicio, fim
    s.add(RegistoAtividade(gabinete_id=p.gabinete_id, utilizador_id=utilizador_id, entidade="subscricao",
                           acao="pagamento", dados={"plano": p.plano, "ciclo": p.ciclo, "total_cents": p.valor_cents + p.iva_cents}))


def confirmar_simulado(s: Session, gabinete_id, utilizador_id, pagamento_id, sucesso: bool) -> dict:
    cfg = get_settings()
    if cfg.pagamentos_modo != "simulado" or cfg.producao:
        raise ErroAuth(403, "so_simulado", "Só disponível no modo de pagamento simulado.")
    _exigir_gestor(s, gabinete_id, utilizador_id)
    p = _pagamento(s, gabinete_id, pagamento_id)
    if p.estado != "pendente":
        raise ErroAuth(409, "pagamento_fechado", "Este pagamento já foi tratado. Volte à página da subscrição.")
    if sucesso:
        _aplicar(s, p, utilizador_id)
    else:
        p.estado = "falhado"
    return _pagamento_json(p)


def cancelar(s: Session, gabinete_id, utilizador_id) -> dict:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    sub = obter(s, gabinete_id)
    if estado(sub) != "ativa":
        raise ErroAuth(409, "nada_a_cancelar", "Não há nenhuma subscrição paga para cancelar.")
    sub.cancelar_no_fim = True
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="subscricao", acao="cancelada", dados={}))
    return detalhe(s, gabinete_id, utilizador_id)


def retomar(s: Session, gabinete_id, utilizador_id) -> dict:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    sub = obter(s, gabinete_id)
    if estado(sub) != "ativa" or not sub.cancelar_no_fim:
        raise ErroAuth(409, "nada_a_retomar", "A subscrição não está marcada para terminar.")
    sub.cancelar_no_fim = False
    return detalhe(s, gabinete_id, utilizador_id)
