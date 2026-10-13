"""Resumo do IVA das compras de uma empresa, para apoiar a declaração periódica.

Só conta faturas conferidas (ou já exportadas). Mostra:
- IVA dedutível sugerido por campo do quadro 06 da declaração periódica:
    20 imobilizado (contas 43, 44, 45)
    21 / 23 / 22 existências à taxa reduzida / intermédia / normal (contas 31 a 39)
    24 outros bens e serviços (o resto)
- base e IVA por espaço fiscal e taxa, por tratamento (dedutível, 50%, não dedutível…) e por conta.
É uma sugestão para conferir: a classificação final é do contabilista.
"""
from __future__ import annotations

import io
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..empresas.servico import MESES, euros
from ..models import ContaSNC, Empresa, Fatura

CENT = Decimal("0.01")
DEDUCAO = {"dedutivel": Decimal("1"), "dedutivel_50": Decimal("0.5")}
TRATAMENTOS = {"dedutivel": "Dedutível", "dedutivel_50": "Dedutível a 50%", "nao_dedutivel": "Não dedutível",
               "isento": "Isento", "autoliquidacao": "Autoliquidação", "por_definir": "Por definir"}
TAXAS = {"normal": "Normal", "intermedia": "Intermédia", "reduzida": "Reduzida", "isenta": "Isenta", "nao_sujeita": "Não sujeita"}
ESPACOS = {"PT": "Continente", "PT-AC": "Açores", "PT-MA": "Madeira"}
CAMPOS = [("20", "Imobilizado"), ("21", "Existências à taxa reduzida"), ("23", "Existências à taxa intermédia"),
          ("22", "Existências à taxa normal"), ("24", "Outros bens e serviços")]
TRIMESTRES = {1: "1.º trimestre", 2: "2.º trimestre", 3: "3.º trimestre", 4: "4.º trimestre"}


def _campo(conta: str | None, tipo_taxa: str) -> str:
    c = conta or ""
    if c[:2] in ("43", "44", "45"):
        return "20"
    if c[:1] == "3":
        return {"reduzida": "21", "intermedia": "23"}.get(tipo_taxa, "22")
    return "24"


def intervalo(mes: date, tipo: str) -> tuple[date, date, str]:
    """(primeiro mês, primeiro mês seguinte, rótulo)."""
    mes = mes.replace(day=1)
    if tipo == "trimestre":
        t = (mes.month - 1) // 3 + 1
        ini = date(mes.year, 3 * t - 2, 1)
        fim = date(mes.year + (t == 4), 1 if t == 4 else 3 * t + 1, 1)
        return ini, fim, f"{TRIMESTRES[t]} de {mes.year}"
    fim = date(mes.year + (mes.month == 12), 1 if mes.month == 12 else mes.month + 1, 1)
    return mes, fim, f"{MESES[mes.month - 1]} de {mes.year}"


def resumo(s: Session, empresa_id, mes: date, tipo: str | None = None) -> dict:
    e = s.get(Empresa, empresa_id)
    if not e:
        raise ErroAuth(404, "nao_encontrada", "Empresa não encontrada.")
    tipo = tipo or ("trimestre" if e.periodicidade_iva == "trimestral" else "mes")
    if tipo not in ("mes", "trimestre"):
        raise ErroAuth(422, "tipo_invalido", "Escolha mês ou trimestre.")
    ini, fim, rotulo = intervalo(mes, tipo)
    todas = s.scalars(select(Fatura).where(Fatura.empresa_id == e.id, Fatura.periodo >= ini, Fatura.periodo < fim,
                                           Fatura.eliminada_em.is_(None), Fatura.estado != "rejeitada")).all()
    contas = dict(s.execute(select(ContaSNC.codigo, ContaSNC.descricao)).all())
    validas = [f for f in todas if f.estado in ("conferida", "exportada")]
    z = lambda: {"base": Decimal("0"), "iva": Decimal("0"), "dedutivel": Decimal("0")}
    campos, taxas, trat, por_conta = defaultdict(Decimal), defaultdict(z), defaultdict(z), defaultdict(z)
    tot = z()
    nc = 0
    for f in validas:
        sinal = Decimal("-1") if f.tipo_documento == "NC" else Decimal("1")
        nc += f.tipo_documento == "NC"
        ded = DEDUCAO.get(f.tratamento_iva, Decimal("0"))
        for l in f.linhas_iva:
            base, iva = l.base * sinal, l.iva * sinal
            d = (iva * ded).quantize(CENT)
            for alvo in (taxas[(l.espaco_fiscal, l.tipo_taxa, l.taxa)], trat[f.tratamento_iva], por_conta[f.conta_codigo or ""], tot):
                alvo["base"] += base
                alvo["iva"] += iva
                alvo["dedutivel"] += d
            if d:
                campos[_campo(f.conta_codigo, l.tipo_taxa)] += d
    fmt = lambda v: {k: euros(x) for k, x in v.items()} | {f"{k}_n": float(x) for k, x in v.items()}
    return {
        "empresa": {"id": str(e.id), "nome": e.nome, "nif": e.nif, "periodicidade_iva": e.periodicidade_iva},
        "tipo": tipo, "periodo": ini.isoformat(), "periodo_txt": rotulo,
        "faturas": len(validas), "por_conferir": sum(1 for f in todas if f.estado == "por_conferir"), "notas_credito": nc,
        "totais": fmt(tot) | {"nao_dedutivel": euros(tot["iva"] - tot["dedutivel"])},
        "campos": [{"campo": c, "nome": n, "valor": euros(campos[c]), "valor_n": float(campos[c])} for c, n in CAMPOS],
        "taxas": [{"espaco": ESPACOS.get(es, es), "taxa": TAXAS.get(tt, tt), "pct": float(p) if p is not None else None, **fmt(v)}
                  for (es, tt, p), v in sorted(taxas.items(), key=lambda x: (x[0][0], -(x[0][2] or 0)))],
        "tratamentos": [{"id": k, "nome": TRATAMENTOS.get(k, k), **fmt(v)} for k, v in trat.items()],
        "contas": [{"conta": k or "—", "nome": contas.get(k, "Sem conta"), **fmt(v)} for k, v in sorted(por_conta.items())],
    }


def xlsx(r: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumo do IVA"
    negrito, cab_font, cab_fill = Font(bold=True), Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4353E8")

    def titulo(txt):
        ws.append([])
        ws.append([txt])
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)

    def tabela(cab, linhas):
        ws.append(cab)
        for c in ws[ws.max_row]:
            c.font, c.fill = cab_font, cab_fill
        for l in linhas:
            ws.append(l)
            for c in ws[ws.max_row][1:]:
                if isinstance(c.value, float):
                    c.number_format = '#,##0.00 "€";-#,##0.00 "€"'

    ws.append([f"Resumo do IVA das compras — {r['empresa']['nome']} (NIF {r['empresa']['nif']})"])
    ws.cell(1, 1).font = Font(bold=True, size=14)
    ws.append([f"{r['periodo_txt']} · {r['faturas']} faturas conferidas"
               + (f" · {r['por_conferir']} ainda por conferir (não incluídas)" if r["por_conferir"] else "")])
    titulo("IVA dedutível sugerido (quadro 06 da declaração periódica)")
    tabela(["Campo", "Descrição", "IVA dedutível"], [[c["campo"], c["nome"], c["valor_n"]] for c in r["campos"]])
    ws.append(["", "Total", r["totais"]["dedutivel_n"]])
    ws.cell(ws.max_row, 2).font = negrito
    ws.cell(ws.max_row, 3).number_format = '#,##0.00 "€"'
    titulo("Por espaço fiscal e taxa")
    tabela(["Espaço", "Taxa", "%", "Base", "IVA", "IVA dedutível"],
           [[t["espaco"], t["taxa"], t["pct"], t["base_n"], t["iva_n"], t["dedutivel_n"]] for t in r["taxas"]])
    titulo("Por tratamento do IVA")
    tabela(["Tratamento", "Base", "IVA", "IVA dedutível"], [[t["nome"], t["base_n"], t["iva_n"], t["dedutivel_n"]] for t in r["tratamentos"]])
    titulo("Por conta SNC")
    tabela(["Conta", "Descrição", "Base", "IVA", "IVA dedutível"],
           [[c["conta"], c["nome"], c["base_n"], c["iva_n"], c["dedutivel_n"]] for c in r["contas"]])
    ws.append([])
    ws.append(["Sugestão calculada a partir das faturas conferidas. Confirme antes de submeter a declaração."])
    for col, w in zip("ABCDEF", (26, 34, 16, 16, 16, 16)):
        ws.column_dimensions[col].width = w
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
