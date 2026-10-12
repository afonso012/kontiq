"""Faturas: carregar documentos, ler o QR, validar, classificar e conferir.

Tudo corre numa sessão isolada no gabinete (RLS). As funções levantam
`ErroAuth` (status, código, mensagem, campo) com texto pronto a mostrar.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..core import armazenamento
from ..core.config import get_settings
from ..domain.nif import nif_valido
from ..domain.qr_at import QRInvalido, ler_qr
from ..domain.validacao import validar
from ..empresas.servico import MESES, euros
from ..models import (
    AcessoPortal, Categoria, ContaSNC, Documento, Empresa, Fatura, Fornecedor, LinhaIVA, ProblemaFatura,
    RegistoAtividade, RegraFornecedor, Utilizador,
)
from ..models import enums as E
from . import leitura

MAX_BYTES = 20 * 1024 * 1024
MAX_FICHEIROS = 30
EXT = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic"}
TAXAS_PT = {Decimal("23"): "normal", Decimal("13"): "intermedia", Decimal("6"): "reduzida", Decimal("0"): "isenta"}
NOMES_TIPO = {"FT": "Fatura", "FS": "Fatura simplificada", "FR": "Fatura-recibo", "NC": "Nota de crédito",
              "ND": "Nota de débito", "VD": "Venda a dinheiro", "EST": "Estrangeira", "OUTRO": "Outro"}
TRATAMENTOS = {"dedutivel": "Dedutível a 100%", "dedutivel_50": "Dedutível a 50%", "nao_dedutivel": "Não dedutível",
               "isento": "Isento", "autoliquidacao": "Autoliquidação", "por_definir": "Por definir"}


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _dec(v, campo: str) -> Decimal:
    try:
        d = Decimal(str(v).replace(",", ".")) if v not in (None, "") else Decimal("0")
    except InvalidOperation:
        raise ErroAuth(422, "valor_invalido", "Valor inválido.", campo)
    if abs(d) > Decimal("9999999999"):
        raise ErroAuth(422, "valor_invalido", "Valor demasiado grande.", campo)
    return d.quantize(Decimal("0.01"))


def _registar(s: Session, f_or_doc, utilizador_id, acao: str, dados: dict | None = None, entidade="fatura") -> None:
    s.add(RegistoAtividade(gabinete_id=f_or_doc.gabinete_id, utilizador_id=utilizador_id, entidade=entidade,
                           entidade_id=f_or_doc.id, acao=acao, dados=dados))


def _empresa(s: Session, empresa_id) -> Empresa:
    e = s.get(Empresa, empresa_id)
    if not e:
        raise ErroAuth(404, "nao_encontrada", "Empresa não encontrada.")
    return e


def _fatura(s: Session, fatura_id) -> Fatura:
    f = s.get(Fatura, fatura_id)
    if not f or f.eliminada_em:
        raise ErroAuth(404, "nao_encontrada", "Fatura não encontrada.")
    return f


# ---------------------------------------------------------------- classificação

def _regra(s: Session, fornecedor_id, empresa_id) -> RegraFornecedor | None:
    return s.scalar(select(RegraFornecedor).where(
        RegraFornecedor.fornecedor_id == fornecedor_id,
        or_(RegraFornecedor.empresa_id == empresa_id, RegraFornecedor.empresa_id.is_(None)))
        .order_by(RegraFornecedor.empresa_id.is_(None)).limit(1))


def _aplicar_regra(s: Session, f: Fatura) -> None:
    if not f.fornecedor_id:
        return
    r = _regra(s, f.fornecedor_id, f.empresa_id)
    if r:
        f.categoria_id, f.conta_codigo, f.tratamento_iva, f.origem_classificacao = (
            r.categoria_id, r.conta_codigo, r.tratamento_iva, "regra")


def _fornecedor(s: Session, gabinete_id, pais: str, nif: str, nome: str | None) -> Fornecedor:
    forn = s.scalar(select(Fornecedor).where(Fornecedor.pais == pais, Fornecedor.nif == nif))
    if not forn:
        forn = Fornecedor(gabinete_id=gabinete_id, pais=pais, nif=nif, nome=(nome or f"Fornecedor {nif}")[:200])
        s.add(forn)
        s.flush()
    elif nome and nome.strip() and nome.strip() != forn.nome:
        forn.nome = nome.strip()[:200]
    return forn


def opcoes(s: Session) -> dict:
    cats = s.scalars(select(Categoria).order_by(Categoria.nome)).all()
    contas = s.scalars(select(ContaSNC).where(ContaSNC.ativa.is_(True)).order_by(ContaSNC.codigo)).all()
    return {
        "categorias": [{"id": str(c.id), "nome": c.nome, "conta": c.conta_codigo, "tratamento": c.tratamento_iva} for c in cats],
        "contas": [{"codigo": c.codigo, "descricao": c.descricao} for c in contas],
        "tratamentos": [{"id": k, "nome": v} for k, v in TRATAMENTOS.items()],
        "tipos": [{"id": k, "nome": v} for k, v in NOMES_TIPO.items()],
    }


# ---------------------------------------------------------------- validação

def _norm_numero(n: str | None) -> str:
    return re.sub(r"\s+", "", (n or "").upper())


def revalidar(s: Session, f: Fatura, empresa: Empresa) -> None:
    """Recalcula os problemas da fatura. Mantém os que alguém já resolveu à mão."""
    novos = {p.codigo: p for p in validar(
        pais_fornecedor=f.pais_fornecedor, nif_fornecedor=f.nif_fornecedor, base_total=f.base_total,
        iva_total=f.iva_total, total=f.total, data_emissao=f.data_emissao, tipo_documento=f.tipo_documento,
        tratamento_iva=f.tratamento_iva, conta_codigo=f.conta_codigo)}
    extra: list[tuple[str, str, str]] = []
    if f.nif_adquirente and f.nif_adquirente not in (empresa.nif, "999999990"):
        extra.append(("adquirente_diferente", "aviso",
                      f"A fatura foi emitida ao NIF {f.nif_adquirente}, não ao da empresa ({empresa.nif})."))
    elif f.nif_adquirente == "999999990":
        extra.append(("consumidor_final", "aviso", "Fatura sem NIF da empresa (consumidor final): o IVA pode não ser dedutível."))
    if f.numero and f.nif_fornecedor and f.estado != "rejeitada":
        outra = s.scalar(select(Fatura).where(
            Fatura.empresa_id == f.empresa_id, Fatura.id != f.id, Fatura.eliminada_em.is_(None),
            Fatura.estado != "rejeitada", Fatura.nif_fornecedor == f.nif_fornecedor,
            func.upper(func.regexp_replace(Fatura.numero, r"\s+", "", "g")) == _norm_numero(f.numero),
            or_(Fatura.criado_em < f.criado_em, and_(Fatura.criado_em == f.criado_em, Fatura.id < f.id)))
            .order_by(Fatura.criado_em).limit(1))
        if outra:
            quando = outra.criado_em.astimezone().strftime("%d/%m")
            extra.append(("duplicado", "erro", f"Já existe a {outra.numero} deste fornecedor, carregada a {quando}."))
    for codigo, nivel, mensagem in extra:
        novos[codigo] = type("P", (), {"codigo": codigo, "nivel": nivel, "mensagem": mensagem})()

    resolvidos = {p.codigo for p in f.problemas if p.resolvido}
    for p in list(f.problemas):
        if not p.resolvido and p.codigo not in novos:
            f.problemas.remove(p)
    abertos = {p.codigo: p for p in f.problemas if not p.resolvido}
    for codigo, p in novos.items():
        if codigo in abertos:
            abertos[codigo].mensagem, abertos[codigo].nivel = p.mensagem, p.nivel
        elif codigo not in resolvidos:
            f.problemas.append(ProblemaFatura(gabinete_id=f.gabinete_id, codigo=codigo, nivel=p.nivel, mensagem=p.mensagem))


# ---------------------------------------------------------------- carregar

@dataclass
class Resultado:
    nome: str
    estado: str           # "lida" | "manual" | "repetido" | "erro"
    mensagem: str
    fatura_id: str | None = None
    fornecedor: str | None = None
    numero: str | None = None
    total: str | None = None
    metodo: str | None = None


def carregar(s: Session, gabinete_id, utilizador_id, empresa_id, ficheiros: list[tuple[str, bytes]],
             periodo: date, canal: str = "upload") -> list[Resultado]:
    empresa = _empresa(s, empresa_id)
    if len(ficheiros) > MAX_FICHEIROS:
        raise ErroAuth(422, "demasiados_ficheiros", f"Carregue no máximo {MAX_FICHEIROS} ficheiros de cada vez.")
    out: list[Resultado] = []
    for nome, dados in ficheiros:
        nome = (nome or "documento").replace("/", "_").replace("\\", "_")[-200:]
        if len(dados) > MAX_BYTES:
            out.append(Resultado(nome, "erro", "Ficheiro maior do que 20 MB."))
            continue
        mime = leitura.tipo_por_conteudo(dados)
        if not mime:
            out.append(Resultado(nome, "erro", "Formato não suportado. Use PDF, JPG, PNG ou HEIC."))
            continue
        sha = hashlib.sha256(dados).hexdigest()
        existente = s.scalar(select(Documento).where(Documento.empresa_id == empresa.id, Documento.sha256 == sha))
        if existente:
            f_exist = s.scalar(select(Fatura).where(Fatura.documento_id == existente.id).limit(1))
            out.append(Resultado(nome, "repetido", "Este ficheiro já tinha sido carregado.",
                                 str(f_exist.id) if f_exist else None))
            continue
        chave = f"{gabinete_id}/{empresa.id}/{sha}.{EXT[mime]}"
        armazenamento.guardar(chave, dados)
        doc = Documento(gabinete_id=gabinete_id, empresa_id=empresa.id, chave_armazenamento=chave, nome_original=nome,
                        tipo_mime=mime, tamanho_bytes=len(dados), sha256=sha, canal=canal, enviado_por=utilizador_id)
        s.add(doc)
        s.flush()
        lido = leitura.ler(dados, mime)
        if lido.erro:
            # Guardamos na mesma: o contabilista pode abrir e preencher.
            f = _nova_fatura_manual(s, gabinete_id, empresa, doc, periodo)
            out.append(Resultado(nome, "manual", lido.erro, str(f.id), metodo="manual"))
            continue
        q = None
        if lido.qr:
            try:
                q = ler_qr(lido.qr)
            except QRInvalido:
                q = None
        if q:
            f = _fatura_do_qr(s, gabinete_id, empresa, doc, q, lido)
            forn = s.get(Fornecedor, f.fornecedor_id) if f.fornecedor_id else None
            out.append(Resultado(nome, "lida", "Lida pelo código QR.", str(f.id), forn.nome if forn else None,
                                 f.numero, euros(f.total), "qr"))
        else:
            f = _nova_fatura_manual(s, gabinete_id, empresa, doc, periodo)
            out.append(Resultado(nome, "manual", "Sem código QR: preencha os dados ao conferir.", str(f.id), metodo="manual"))
        _registar(s, f, utilizador_id, "carregada", {"documento": nome, "metodo": f.metodo_leitura})
    return out


def _nova_fatura_manual(s: Session, gabinete_id, empresa: Empresa, doc: Documento, periodo: date) -> Fatura:
    f = Fatura(gabinete_id=gabinete_id, empresa_id=empresa.id, documento_id=doc.id, periodo=periodo.replace(day=1),
               criado_em=agora(), metodo_leitura="manual", tipo_documento="FT", estado="por_conferir", origem_classificacao="manual")
    s.add(f)
    s.flush()
    revalidar(s, f, empresa)
    return f


def _fatura_do_qr(s: Session, gabinete_id, empresa: Empresa, doc: Documento, q, lido) -> Fatura:
    forn = s.scalar(select(Fornecedor).where(Fornecedor.pais == "PT", Fornecedor.nif == q.nif_emitente))
    nome = leitura.nome_provavel_fornecedor(lido.texto, q.nif_emitente)
    if not forn:
        forn = _fornecedor(s, gabinete_id, "PT", q.nif_emitente, nome)
    elif nome and forn.nome == f"Fornecedor {forn.nif}":
        forn.nome = nome[:200]  # ainda só tínhamos o NIF
    tipo = q.tipo_documento if q.tipo_documento in E.TIPOS_DOCUMENTO else "OUTRO"
    data = q.data_emissao
    f = Fatura(gabinete_id=gabinete_id, empresa_id=empresa.id, documento_id=doc.id, fornecedor_id=forn.id,
               criado_em=agora(), periodo=(data or date.today()).replace(day=1), tipo_documento=tipo, numero=q.numero, atcud=q.atcud,
               data_emissao=data, nif_fornecedor=q.nif_emitente, pais_fornecedor="PT", nif_adquirente=q.nif_adquirente,
               base_total=sum((l.base for l in q.linhas_iva), Decimal("0")), iva_total=q.total_impostos or
               sum((l.iva for l in q.linhas_iva), Decimal("0")), total=q.total, metodo_leitura="qr",
               confianca=Decimal("1"), qr_texto=lido.qr, estado="por_conferir", origem_classificacao="sugestao")
    for l in q.linhas_iva:
        f.linhas_iva.append(LinhaIVA(gabinete_id=gabinete_id, espaco_fiscal=l.espaco_fiscal, tipo_taxa=l.tipo_taxa,
                                     taxa=l.taxa, base=l.base, iva=l.iva))
    if q.nao_sujeito:
        f.base_total += q.nao_sujeito
        f.linhas_iva.append(LinhaIVA(gabinete_id=gabinete_id, espaco_fiscal="PT", tipo_taxa="nao_sujeita",
                                     taxa=None, base=q.nao_sujeito, iva=Decimal("0")))
    s.add(f)
    s.flush()
    _aplicar_regra(s, f)
    revalidar(s, f, empresa)
    return f


# ---------------------------------------------------------------- listar e ver

def _por_preencher(f: Fatura) -> bool:
    return f.metodo_leitura == "manual" and not f.nif_fornecedor and not f.total


def _estado_vista(f: Fatura) -> str:
    if f.estado in ("conferida", "exportada"):
        return "ok"
    if f.estado == "rejeitada":
        return "rejeitada"
    if _por_preencher(f):
        return "warn"
    return "bad" if any(p.nivel == "erro" and not p.resolvido for p in f.problemas) else "warn"


def lista_empresa(s: Session, empresa_id, mes: date) -> dict:
    e = _empresa(s, empresa_id)
    mes = mes.replace(day=1)
    faturas = s.scalars(select(Fatura).where(Fatura.empresa_id == e.id, Fatura.periodo == mes, Fatura.eliminada_em.is_(None))
                        .order_by(Fatura.data_emissao.asc().nulls_first(), Fatura.criado_em)).all()
    fornecedores = {f.id: f.nome for f in s.scalars(select(Fornecedor).where(
        Fornecedor.id.in_([x.fornecedor_id for x in faturas if x.fornecedor_id])))} if faturas else {}
    contas = dict(s.execute(select(ContaSNC.codigo, ContaSNC.descricao)).all())
    acesso = s.execute(select(Utilizador.nome).join(AcessoPortal, AcessoPortal.utilizador_id == Utilizador.id)
                       .where(AcessoPortal.empresa_id == e.id).limit(1)).scalar()
    linhas, validas = [], [f for f in faturas if f.estado != "rejeitada"]
    for f in faturas:
        abertos = [p for p in f.problemas if not p.resolvido]
        principal = next((p for p in abertos if p.nivel == "erro"), None) or next(
            (p for p in abertos if p.codigo != "sem_classificacao"), None)
        linhas.append({
            "id": str(f.id), "data": f.data_emissao.isoformat() if f.data_emissao else None,
            "fornecedor": fornecedores.get(f.fornecedor_id) or (f"NIF {f.nif_fornecedor}" if f.nif_fornecedor else None),
            "nif": f.nif_fornecedor, "numero": f.numero, "tipo": f.tipo_documento, "metodo": f.metodo_leitura,
            "confianca": float(f.confianca) if f.confianca is not None else None,
            "conta": f.conta_codigo, "conta_nome": contas.get(f.conta_codigo) if f.conta_codigo else None,
            "iva": euros(f.iva_total), "total": euros(f.total), "total_n": float(f.total),
            "estado": _estado_vista(f), "nota": principal.mensagem if principal else None,
            "por_preencher": _por_preencher(f),
            "nota_curta": ({"duplicado": "Possível duplicado", "nif_invalido": "NIF inválido",
                           "contas_nao_batem": "Totais não batem", "sem_data": "Sem data", "sem_total": "Sem total",
                           "iva_estrangeiro": "IVA estrangeiro", "adquirente_diferente": "Outro adquirente",
                           "consumidor_final": "Consumidor final", "sem_nif": "Sem NIF"}.get(principal.codigo) if principal else None)
            if not _por_preencher(f) else "Por preencher",
        })
    n_ok = sum(1 for f in validas if f.estado in ("conferida", "exportada"))
    s_conf = get_settings()
    return {
        "empresa": {"id": str(e.id), "nome": e.nome, "nif": e.nif, "periodicidade_iva": e.periodicidade_iva,
                    "portal": acesso, "email_entrada": f"{e.caixa_email}@{s_conf.dominio_email_entrada}"},
        "periodo": mes.isoformat(), "periodo_txt": f"{MESES[mes.month - 1]} de {mes.year}",
        "totais": {
            "faturas": len(validas), "total_txt": euros(sum((f.total for f in validas), Decimal("0"))),
            "iva_txt": euros(sum((f.iva_total for f in validas), Decimal("0"))),
            "conferidas": n_ok, "por_conferir": len(validas) - n_ok,
            "qr": sum(1 for f in validas if f.metodo_leitura == "qr" and f.estado == "por_conferir"),
            "manual": sum(1 for f in validas if f.metodo_leitura == "manual" and f.estado == "por_conferir"),
            "problemas": sum(1 for f in validas if _estado_vista(f) == "bad"),
            "por_preencher": sum(1 for f in validas if _por_preencher(f) and f.estado == "por_conferir"),
        },
        "faturas": linhas,
    }


def _fila(s: Session, f: Fatura) -> list[str]:
    ids = s.scalars(select(Fatura.id).where(
        Fatura.empresa_id == f.empresa_id, Fatura.periodo == f.periodo, Fatura.eliminada_em.is_(None),
        or_(Fatura.estado == "por_conferir", Fatura.id == f.id))
        .order_by(Fatura.data_emissao.asc().nulls_first(), Fatura.criado_em, Fatura.numero)).all()
    return [str(i) for i in ids]


def detalhe(s: Session, fatura_id) -> dict:
    f = _fatura(s, fatura_id)
    e = s.get(Empresa, f.empresa_id)
    forn = s.get(Fornecedor, f.fornecedor_id) if f.fornecedor_id else None
    doc = s.get(Documento, f.documento_id) if f.documento_id else None
    n_forn = s.scalar(select(func.count()).select_from(Fatura).where(
        Fatura.fornecedor_id == f.fornecedor_id, Fatura.eliminada_em.is_(None))) if forn else 0
    regra = _regra(s, f.fornecedor_id, f.empresa_id) if forn else None
    fila = _fila(s, f)
    pos = fila.index(str(f.id)) if str(f.id) in fila else -1
    dup = next((p for p in f.problemas if p.codigo == "duplicado" and not p.resolvido), None)
    original = None
    if dup:
        o = s.scalar(select(Fatura).where(Fatura.empresa_id == f.empresa_id, Fatura.id != f.id,
                                          Fatura.nif_fornecedor == f.nif_fornecedor, Fatura.estado != "rejeitada",
                                          Fatura.eliminada_em.is_(None),
                                          func.upper(func.regexp_replace(Fatura.numero, r"\s+", "", "g")) == _norm_numero(f.numero))
                     .order_by(Fatura.criado_em).limit(1))
        original = str(o.id) if o else None
    return {
        "id": str(f.id), "estado": f.estado, "estado_vista": _estado_vista(f),
        "empresa": {"id": str(e.id), "nome": e.nome, "nif": e.nif},
        "periodo": f.periodo.isoformat(),
        "documento": {"id": str(doc.id), "nome": doc.nome_original, "tipo": doc.tipo_mime, "canal": doc.canal,
                      "recebido": doc.criado_em.isoformat()} if doc else None,
        "metodo": f.metodo_leitura, "confianca": float(f.confianca) if f.confianca is not None else None,
        "fornecedor": {"nome": forn.nome if forn else "", "nif": f.nif_fornecedor or "", "pais": f.pais_fornecedor,
                       "faturas": n_forn, "conhecido": n_forn > 1},
        "tipo_documento": f.tipo_documento, "numero": f.numero or "", "atcud": f.atcud or "",
        "data": f.data_emissao.isoformat() if f.data_emissao else "", "nif_adquirente": f.nif_adquirente,
        "linhas": [{"espaco": l.espaco_fiscal, "tipo_taxa": l.tipo_taxa, "taxa": float(l.taxa) if l.taxa is not None else None,
                    "base": f"{l.base:.2f}", "iva": f"{l.iva:.2f}"} for l in f.linhas_iva],
        "base_total": f"{f.base_total:.2f}", "iva_total": f"{f.iva_total:.2f}", "total": f"{f.total:.2f}",
        "total_txt": euros(f.total),
        "categoria_id": str(f.categoria_id) if f.categoria_id else None, "conta": f.conta_codigo,
        "tratamento_iva": f.tratamento_iva, "origem_classificacao": f.origem_classificacao,
        "regra": {"criada": regra.criado_em.isoformat(), "geral": regra.empresa_id is None} if regra else None,
        "notas": f.notas or "",
        "problemas": [{"id": str(p.id), "codigo": p.codigo, "nivel": p.nivel, "mensagem": p.mensagem}
                      for p in f.problemas if not p.resolvido],
        "duplicado_de": original,
        "fila": {"posicao": pos + 1, "total": len(fila), "anterior": fila[pos - 1] if pos > 0 else None,
                 # A seguinte por conferir; no fim da lista, volta ao princípio.
                 "seguinte": (fila[pos + 1] if 0 <= pos < len(fila) - 1 else
                              next((i for i in fila if i != str(f.id)), None))},
        "conferida_em": f.conferida_em.isoformat() if f.conferida_em else None,
    }


# ---------------------------------------------------------------- editar, conferir, rejeitar

def atualizar(s: Session, gabinete_id, utilizador_id, fatura_id, d: dict) -> Fatura:
    f = _fatura(s, fatura_id)
    if f.estado == "exportada":
        raise ErroAuth(409, "exportada", "Esta fatura já foi exportada e não pode ser alterada.")
    e = s.get(Empresa, f.empresa_id)
    pais = (d.get("pais") or f.pais_fornecedor or "PT").upper()[:2]
    nif = re.sub(r"\s", "", d.get("nif") or "")
    if pais == "PT" and nif and not re.fullmatch(r"\d{9}", nif):
        raise ErroAuth(422, "nif_invalido", "O NIF português tem 9 dígitos.", "nif")
    nome_forn = (d.get("fornecedor") or "").strip()
    if nif:
        forn = _fornecedor(s, gabinete_id, pais, nif[:30], nome_forn or None)
        mudou_forn = forn.id != f.fornecedor_id
        f.fornecedor_id, f.nif_fornecedor, f.pais_fornecedor = forn.id, forn.nif, pais
    else:
        mudou_forn = False
        f.fornecedor_id, f.nif_fornecedor, f.pais_fornecedor = None, None, pais
    tipo = d.get("tipo_documento") or f.tipo_documento
    if tipo not in E.TIPOS_DOCUMENTO:
        raise ErroAuth(422, "tipo_invalido", "Tipo de documento inválido.", "tipo_documento")
    f.tipo_documento = tipo
    f.numero = (d.get("numero") or "").strip()[:80] or None
    f.atcud = (d.get("atcud") or "").strip()[:80] or None
    if d.get("data"):
        try:
            f.data_emissao = date.fromisoformat(d["data"])
        except ValueError:
            raise ErroAuth(422, "data_invalida", "Data inválida.", "data")
        if f.data_emissao > date.today():
            raise ErroAuth(422, "data_futura", "A data da fatura não pode ser no futuro.", "data")
        f.periodo = f.data_emissao.replace(day=1)
    else:
        f.data_emissao = None
    if "linhas" in d:
        for l in list(f.linhas_iva):
            f.linhas_iva.remove(l)
        for i, l in enumerate(d["linhas"] or []):
            base, iva = _dec(l.get("base"), f"linhas.{i}.base"), _dec(l.get("iva"), f"linhas.{i}.iva")
            if base == 0 and iva == 0:
                continue
            taxa = Decimal(str(l["taxa"])) if l.get("taxa") not in (None, "") else None
            tipo_taxa = l.get("tipo_taxa") or (TAXAS_PT.get(taxa) if taxa is not None else None) or "normal"
            if tipo_taxa not in E.TIPOS_TAXA:
                tipo_taxa = "normal"
            esp = l.get("espaco") if l.get("espaco") in E.ESPACOS_FISCAIS else "PT"
            f.linhas_iva.append(LinhaIVA(gabinete_id=f.gabinete_id, espaco_fiscal=esp, tipo_taxa=tipo_taxa,
                                         taxa=taxa, base=base, iva=iva))
        f.base_total = sum((l.base for l in f.linhas_iva), Decimal("0"))
        f.iva_total = sum((l.iva for l in f.linhas_iva), Decimal("0"))
    if "total" in d:
        f.total = _dec(d.get("total"), "total")
    # Classificação
    cat_id = d.get("categoria_id")
    antes_cat = f.categoria_id
    f.categoria_id = uuid.UUID(cat_id) if cat_id else None
    conta = (d.get("conta") or "").strip() or None
    if conta and not s.scalar(select(ContaSNC.id).where(ContaSNC.codigo == conta)):
        raise ErroAuth(422, "conta_invalida", "Conta SNC desconhecida.", "conta")
    trat = d.get("tratamento_iva") or "por_definir"
    if trat not in E.TRATAMENTOS_IVA:
        raise ErroAuth(422, "tratamento_invalido", "Tratamento do IVA inválido.", "tratamento_iva")
    if (conta, trat) != (f.conta_codigo, f.tratamento_iva) or f.categoria_id != antes_cat:
        f.origem_classificacao = "manual"
    f.conta_codigo, f.tratamento_iva = conta, trat
    if mudou_forn and not conta:
        _aplicar_regra(s, f)
    f.notas = (d.get("notas") or "").strip()[:2000] or None
    revalidar(s, f, e)
    _registar(s, f, utilizador_id, "editada")
    return f


def conferir(s: Session, gabinete_id, utilizador_id, fatura_id, lembrar: bool = False) -> Fatura:
    f = _fatura(s, fatura_id)
    if f.estado == "exportada":
        raise ErroAuth(409, "exportada", "Esta fatura já foi exportada.")
    e = s.get(Empresa, f.empresa_id)
    revalidar(s, f, e)
    s.flush()
    erros = [p for p in f.problemas if not p.resolvido and p.nivel == "erro"]
    if erros:
        raise ErroAuth(422, "tem_erros", f"Resolva primeiro: {erros[0].mensagem}")
    if not f.conta_codigo or f.tratamento_iva == "por_definir":
        raise ErroAuth(422, "sem_classificacao", "Escolha a conta SNC e o tratamento do IVA antes de conferir.", "conta")
    f.estado, f.conferida_por, f.conferida_em = "conferida", utilizador_id, agora()
    for p in f.problemas:
        if not p.resolvido and p.codigo == "sem_classificacao":
            p.resolvido = True
    if lembrar and f.fornecedor_id:
        r = s.scalar(select(RegraFornecedor).where(RegraFornecedor.fornecedor_id == f.fornecedor_id,
                                                   RegraFornecedor.empresa_id.is_(None)))
        if r:
            r.categoria_id, r.conta_codigo, r.tratamento_iva = f.categoria_id, f.conta_codigo, f.tratamento_iva
        else:
            s.add(RegraFornecedor(gabinete_id=gabinete_id, fornecedor_id=f.fornecedor_id, empresa_id=None,
                                  categoria_id=f.categoria_id, conta_codigo=f.conta_codigo,
                                  tratamento_iva=f.tratamento_iva, criado_por=utilizador_id))
    _registar(s, f, utilizador_id, "conferida", {"lembrar": lembrar})
    return f


def rejeitar(s: Session, utilizador_id, fatura_id, motivo: str | None) -> Fatura:
    f = _fatura(s, fatura_id)
    if f.estado == "exportada":
        raise ErroAuth(409, "exportada", "Esta fatura já foi exportada.")
    f.estado, f.conferida_por, f.conferida_em = "rejeitada", None, None
    if motivo:
        f.notas = ((f.notas + "\n") if f.notas else "") + f"Rejeitada: {motivo.strip()[:300]}"
    _registar(s, f, utilizador_id, "rejeitada", {"motivo": motivo})
    return f


def reabrir(s: Session, utilizador_id, fatura_id) -> Fatura:
    f = _fatura(s, fatura_id)
    if f.estado == "exportada":
        raise ErroAuth(409, "exportada", "Esta fatura já foi exportada.")
    f.estado, f.conferida_por, f.conferida_em = "por_conferir", None, None
    revalidar(s, f, s.get(Empresa, f.empresa_id))
    _registar(s, f, utilizador_id, "reaberta")
    return f


def resolver_problema(s: Session, utilizador_id, fatura_id, problema_id) -> Fatura:
    f = _fatura(s, fatura_id)
    p = next((p for p in f.problemas if str(p.id) == str(problema_id)), None)
    if not p:
        raise ErroAuth(404, "nao_encontrado", "Problema não encontrado.")
    p.resolvido, p.resolvido_por, p.resolvido_em = True, utilizador_id, agora()
    _registar(s, f, utilizador_id, "problema_resolvido", {"codigo": p.codigo})
    return f


def documento(s: Session, documento_id) -> Documento:
    d = s.get(Documento, documento_id)
    if not d:
        raise ErroAuth(404, "nao_encontrado", "Documento não encontrado.")
    return d
