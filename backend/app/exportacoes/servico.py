"""Exportar as faturas conferidas para o programa de contabilidade.

Formatos desta fase (genéricos, abrem em qualquer programa):
- xlsx: folhas "Faturas", "Linhas de IVA" e "Resumo do IVA" (por empresa e taxa);
- csv:  uma linha por fatura, separador ";" e vírgula decimal (abre bem no Excel em PT);
- zip:  o Excel + os documentos originais arrumados por empresa.

Os formatos de importação próprios (TOConline, Primavera, PHC, Sage) ficam para
quando forem confirmados com gabinetes reais.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..core import armazenamento
from ..empresas.servico import MESES, euros
from ..models import (
    Categoria, ContaSNC, Documento, Empresa, Exportacao, Fatura, Fornecedor, RegistoAtividade, Utilizador,
)

FORMATOS = {"xlsx": "Excel", "csv": "CSV", "zip": "ZIP com documentos"}
DEDUCAO = {"dedutivel": Decimal("1"), "dedutivel_50": Decimal("0.5"), "nao_dedutivel": Decimal("0"),
           "isento": Decimal("0"), "autoliquidacao": Decimal("0"), "por_definir": Decimal("0")}
TRATAMENTOS = {"dedutivel": "Dedutível a 100%", "dedutivel_50": "Dedutível a 50%", "nao_dedutivel": "Não dedutível",
               "isento": "Isento", "autoliquidacao": "Autoliquidação", "por_definir": "Por definir"}
TAXAS = {"normal": "Normal", "intermedia": "Intermédia", "reduzida": "Reduzida", "isenta": "Isenta", "nao_sujeita": "Não sujeita"}
ESPACOS = {"PT": "Continente", "PT-AC": "Açores", "PT-MA": "Madeira"}


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _seguro(nome: str) -> str:
    """Nome de ficheiro/pasta sem caracteres problemáticos."""
    return re.sub(r"[^\w\-. ,&()]+", "_", nome, flags=re.UNICODE).strip(" ._")[:80] or "sem-nome"


def _consulta(s: Session, mes: date, empresa_ids: list[uuid.UUID] | None, incluir_exportadas: bool):
    estados = ("conferida", "exportada") if incluir_exportadas else ("conferida",)
    q = select(Fatura).where(Fatura.periodo == mes, Fatura.eliminada_em.is_(None), Fatura.estado.in_(estados))
    if empresa_ids is not None:
        q = q.where(Fatura.empresa_id.in_(empresa_ids))
    return s.scalars(q.order_by(Fatura.empresa_id, Fatura.data_emissao, Fatura.numero)).all()


# ---------------------------------------------------------------- previsão

def previsao(s: Session, mes: date) -> dict:
    """Por empresa: quantas faturas há prontas, por conferir e já exportadas neste mês."""
    mes = mes.replace(day=1)
    linhas = s.execute(
        select(Empresa.id, Empresa.nome, Empresa.nif,
               func.count(Fatura.id).filter(Fatura.estado == "conferida").label("prontas"),
               func.count(Fatura.id).filter(Fatura.estado == "por_conferir").label("por_conferir"),
               func.count(Fatura.id).filter(Fatura.estado == "exportada").label("exportadas"),
               func.coalesce(func.sum(Fatura.total).filter(Fatura.estado == "conferida"), 0).label("total"))
        .outerjoin(Fatura, (Fatura.empresa_id == Empresa.id) & (Fatura.periodo == mes) & Fatura.eliminada_em.is_(None))
        .where(Empresa.ativa.is_(True)).group_by(Empresa.id).order_by(Empresa.nome)).all()
    return {
        "periodo": mes.isoformat(), "periodo_txt": f"{MESES[mes.month - 1]} de {mes.year}",
        "empresas": [{"id": str(l.id), "nome": l.nome, "nif": l.nif, "prontas": l.prontas, "por_conferir": l.por_conferir,
                      "exportadas": l.exportadas, "total_txt": euros(l.total)} for l in linhas],
        "formatos": [{"id": k, "nome": v} for k, v in FORMATOS.items()],
    }


# ---------------------------------------------------------------- gerar

def _dados(s: Session, faturas: list[Fatura]) -> dict:
    empresas = {e.id: e for e in s.scalars(select(Empresa).where(Empresa.id.in_({f.empresa_id for f in faturas})))}
    forn = {x.id: x for x in s.scalars(select(Fornecedor).where(Fornecedor.id.in_({f.fornecedor_id for f in faturas if f.fornecedor_id})))}
    cats = {c.id: c.nome for c in s.scalars(select(Categoria))}
    contas = dict(s.execute(select(ContaSNC.codigo, ContaSNC.descricao)).all())
    pessoas = dict(s.execute(select(Utilizador.id, Utilizador.nome).where(
        Utilizador.id.in_({f.conferida_por for f in faturas if f.conferida_por}))).all())
    return {"empresas": empresas, "forn": forn, "cats": cats, "contas": contas, "pessoas": pessoas}


def _linhas_fatura(faturas: list[Fatura], d: dict) -> list[list]:
    out = []
    for f in faturas:
        e, fo = d["empresas"][f.empresa_id], d["forn"].get(f.fornecedor_id)
        sinal = Decimal("-1") if f.tipo_documento == "NC" else Decimal("1")
        out.append([
            e.nome, e.nif, f.data_emissao, fo.nome if fo else "", f.nif_fornecedor or "", f.pais_fornecedor,
            f.tipo_documento, f.numero or "", f.atcud or "", f.conta_codigo or "",
            d["contas"].get(f.conta_codigo, ""), d["cats"].get(f.categoria_id, ""), TRATAMENTOS.get(f.tratamento_iva, ""),
            f.base_total * sinal, f.iva_total * sinal, (f.iva_total * DEDUCAO.get(f.tratamento_iva, 0) * sinal).quantize(Decimal("0.01")),
            f.total * sinal, {"qr": "QR da AT", "ia": "IA", "manual": "Manual"}[f.metodo_leitura],
            d["pessoas"].get(f.conferida_por, ""), f.conferida_em.astimezone().replace(tzinfo=None) if f.conferida_em else None,
            (f.notas or "").replace("\n", " "),
        ])
    return out


CAB_FATURAS = ["Empresa", "NIF empresa", "Data", "Fornecedor", "NIF fornecedor", "País", "Tipo", "Número", "ATCUD",
               "Conta SNC", "Descrição da conta", "Categoria", "IVA na declaração", "Base", "IVA", "IVA dedutível",
               "Total", "Leitura", "Conferida por", "Conferida em", "Notas"]


def _xlsx(faturas: list[Fatura], d: dict, titulo: str) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    cab_font, cab_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4353E8")
    euro = '#,##0.00 "€";-#,##0.00 "€"'

    def folha(ws, cab, linhas, dinheiro: set[int], datas: set[int], larguras: dict[int, int]):
        ws.append(cab)
        for c in ws[1]:
            c.font, c.fill, c.alignment = cab_font, cab_fill, Alignment(vertical="center")
        for l in linhas:
            ws.append(l)
        for col in dinheiro:
            for (cell,) in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                cell.number_format = euro
        for col in datas:
            for (cell,) in ws.iter_rows(min_row=2, min_col=col, max_col=col):
                cell.number_format = "dd/mm/yyyy"
        for i in range(1, len(cab) + 1):
            ws.column_dimensions[get_column_letter(i)].width = larguras.get(i, 14)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active
    ws.title = "Faturas"
    folha(ws, CAB_FATURAS, _linhas_fatura(faturas, d), {14, 15, 16, 17}, {3, 20},
          {1: 30, 4: 32, 8: 18, 9: 18, 11: 30, 12: 22, 13: 18, 21: 30})

    ws2 = wb.create_sheet("Linhas de IVA")
    linhas2, resumo = [], defaultdict(lambda: [Decimal("0"), Decimal("0"), Decimal("0")])
    for f in faturas:
        e, fo = d["empresas"][f.empresa_id], d["forn"].get(f.fornecedor_id)
        sinal = Decimal("-1") if f.tipo_documento == "NC" else Decimal("1")
        ded = DEDUCAO.get(f.tratamento_iva, Decimal("0"))
        for l in f.linhas_iva:
            iva_ded = (l.iva * ded * sinal).quantize(Decimal("0.01"))
            linhas2.append([e.nome, f.data_emissao, fo.nome if fo else "", f.numero or "", ESPACOS.get(l.espaco_fiscal, l.espaco_fiscal),
                            TAXAS.get(l.tipo_taxa, l.tipo_taxa), float(l.taxa) if l.taxa is not None else None,
                            l.base * sinal, l.iva * sinal, iva_ded, TRATAMENTOS.get(f.tratamento_iva, "")])
            r = resumo[(e.nome, e.nif, ESPACOS.get(l.espaco_fiscal, l.espaco_fiscal), TAXAS.get(l.tipo_taxa, l.tipo_taxa))]
            r[0] += l.base * sinal
            r[1] += l.iva * sinal
            r[2] += iva_ded
    folha(ws2, ["Empresa", "Data", "Fornecedor", "Número", "Espaço fiscal", "Taxa", "%", "Base", "IVA", "IVA dedutível", "IVA na declaração"],
          linhas2, {8, 9, 10}, {2}, {1: 30, 3: 32, 4: 18, 11: 20})

    ws3 = wb.create_sheet("Resumo do IVA")
    linhas3 = [[k[0], k[1], k[2], k[3], v[0], v[1], v[2]] for k, v in sorted(resumo.items())]
    folha(ws3, ["Empresa", "NIF", "Espaço fiscal", "Taxa", "Base", "IVA", "IVA dedutível"], linhas3, {5, 6, 7}, set(),
          {1: 30, 3: 16})
    ws3.append([])
    ws3.append([titulo])
    ws3.cell(ws3.max_row, 1).font = Font(italic=True, color="5B6075")

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv(faturas: list[Fatura], d: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow(CAB_FATURAS)
    for l in _linhas_fatura(faturas, d):
        w.writerow([
            (f"{v:.2f}".replace(".", ",") if isinstance(v, Decimal)
             else v.strftime("%d/%m/%Y %H:%M") if isinstance(v, datetime)
             else v.strftime("%d/%m/%Y") if isinstance(v, date) else v if v is not None else "")
            for v in l])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # BOM: o Excel reconhece os acentos


def _zip(s: Session, faturas: list[Fatura], d: dict, xlsx: bytes, nome_xlsx: str) -> bytes:
    buf = io.BytesIO()
    usados: set[str] = set()
    docs = {x.id: x for x in s.scalars(select(Documento).where(Documento.id.in_({f.documento_id for f in faturas if f.documento_id})))}
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(nome_xlsx, xlsx)
        for f in faturas:
            doc = docs.get(f.documento_id)
            if not doc:
                continue
            caminho = armazenamento.caminho(doc.chave_armazenamento)
            if not caminho.exists():
                continue
            e, fo = d["empresas"][f.empresa_id], d["forn"].get(f.fornecedor_id)
            ext = doc.chave_armazenamento.rsplit(".", 1)[-1]
            data = f.data_emissao.isoformat() if f.data_emissao else "sem-data"
            base = f"{_seguro(e.nome)}/{data} {_seguro(fo.nome if fo else 'fornecedor')} {_seguro(f.numero or 'sem-numero')}"
            nome, i = f"{base}.{ext}", 2
            while nome in usados:
                nome, i = f"{base} ({i}).{ext}", i + 1
            usados.add(nome)
            z.write(caminho, nome)
    return buf.getvalue()


def exportar(s: Session, gabinete_id, utilizador_id, mes: date, empresa_ids: list[uuid.UUID] | None, formato: str,
             incluir_exportadas: bool, marcar: bool) -> dict:
    if formato not in FORMATOS:
        raise ErroAuth(422, "formato_invalido", "Escolha o formato: Excel, CSV ou ZIP.", "formato")
    mes = mes.replace(day=1)
    faturas = list(_consulta(s, mes, empresa_ids, incluir_exportadas))
    if not faturas:
        raise ErroAuth(422, "nada_para_exportar", "Não há faturas conferidas para exportar com estas escolhas.")
    d = _dados(s, faturas)
    lote = uuid.uuid4()
    rotulo = f"{mes.year}-{mes.month:02d}"
    um = len(d["empresas"]) == 1
    prefixo = _seguro(next(iter(d["empresas"].values())).nome) if um else "Faturas"
    titulo = f"Exportado a {agora().astimezone():%d/%m/%Y %H:%M} · {len(faturas)} faturas · {MESES[mes.month - 1]} de {mes.year}"
    nome_xlsx = f"{prefixo} {rotulo}.xlsx"
    if formato == "csv":
        conteudo, nome, mime = _csv(faturas, d), f"{prefixo} {rotulo}.csv", "text/csv"
    else:
        xlsx = _xlsx(faturas, d, titulo)
        if formato == "xlsx":
            conteudo, nome, mime = xlsx, nome_xlsx, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            conteudo, nome, mime = _zip(s, faturas, d, xlsx, nome_xlsx), f"{prefixo} {rotulo}.zip", "application/zip"
    chave = f"{gabinete_id}/exportacoes/{lote}/{nome}"
    armazenamento.guardar(chave, conteudo)

    por_empresa: dict = defaultdict(int)
    for f in faturas:
        por_empresa[f.empresa_id] += 1
        if marcar and f.estado == "conferida":
            f.estado, f.exportacao_lote = "exportada", lote
    for eid, n in por_empresa.items():
        s.add(Exportacao(gabinete_id=gabinete_id, empresa_id=eid, periodo=mes, formato=formato, num_faturas=n,
                         chave_armazenamento=chave, criado_por=utilizador_id, lote_id=lote, marcou_exportadas=marcar))
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="exportacao", entidade_id=lote,
                           acao="exportada", dados={"formato": formato, "faturas": len(faturas), "periodo": mes.isoformat()}))
    return {"lote": str(lote), "nome": nome, "faturas": len(faturas), "empresas": len(por_empresa), "mime": mime}


# ---------------------------------------------------------------- histórico

def historico(s: Session, limite: int = 30) -> list[dict]:
    linhas = s.execute(
        select(Exportacao.lote_id, func.min(Exportacao.criado_em).label("em"), func.min(Exportacao.formato).label("formato"),
               func.min(Exportacao.periodo).label("periodo"), func.sum(Exportacao.num_faturas).label("faturas"),
               func.count().label("empresas"), func.min(Exportacao.chave_armazenamento).label("chave"),
               func.bool_or(Exportacao.marcou_exportadas).label("marcou"), func.max(Exportacao.desfeita_em).label("desfeita"),
               func.min(Utilizador.nome).label("quem"), func.min(Empresa.nome).label("empresa"))
        .outerjoin(Utilizador, Utilizador.id == Exportacao.criado_por).join(Empresa, Empresa.id == Exportacao.empresa_id)
        .where(Exportacao.lote_id.is_not(None))
        .group_by(Exportacao.lote_id).order_by(func.min(Exportacao.criado_em).desc()).limit(limite)).all()
    return [{"lote": str(l.lote_id), "em": l.em.isoformat(), "formato": l.formato, "formato_nome": FORMATOS.get(l.formato, l.formato),
             "periodo": l.periodo.isoformat(), "periodo_txt": f"{MESES[l.periodo.month - 1]} de {l.periodo.year}",
             "faturas": int(l.faturas), "empresas": l.empresas, "empresa": l.empresa if l.empresas == 1 else None,
             "nome": l.chave.rsplit("/", 1)[-1] if l.chave else None, "quem": l.quem,
             "marcou": l.marcou, "desfeita": l.desfeita.isoformat() if l.desfeita else None} for l in linhas]


def ficheiro(s: Session, lote: uuid.UUID) -> tuple[str, str]:
    chave = s.scalar(select(Exportacao.chave_armazenamento).where(Exportacao.lote_id == lote).limit(1))
    if not chave:
        raise ErroAuth(404, "nao_encontrada", "Exportação não encontrada.")
    return chave, chave.rsplit("/", 1)[-1]


def desfazer(s: Session, utilizador_id, lote: uuid.UUID) -> int:
    """As faturas deste lote voltam a 'conferida' (podem ser corrigidas e exportadas outra vez)."""
    linhas = s.scalars(select(Exportacao).where(Exportacao.lote_id == lote)).all()
    if not linhas:
        raise ErroAuth(404, "nao_encontrada", "Exportação não encontrada.")
    if any(l.desfeita_em for l in linhas):
        raise ErroAuth(409, "ja_desfeita", "Esta exportação já foi desfeita.")
    n = 0
    for f in s.scalars(select(Fatura).where(Fatura.exportacao_lote == lote, Fatura.estado == "exportada")):
        f.estado, f.exportacao_lote = "conferida", None
        n += 1
    for l in linhas:
        l.desfeita_em = agora()
    s.add(RegistoAtividade(gabinete_id=linhas[0].gabinete_id, utilizador_id=utilizador_id, entidade="exportacao",
                           entidade_id=lote, acao="desfeita", dados={"faturas": n}))
    return n
