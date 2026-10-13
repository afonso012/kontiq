"""Lançamentos contabilísticos das faturas de compra, prontos a importar no programa do gabinete.

Cada fatura conferida dá um lançamento no diário de compras:
  débito   conta de gasto/ativo da fatura (base + IVA não dedutível)
  débito   conta de IVA dedutível, por tipo de taxa (só a parte dedutível)
  crédito  conta do fornecedor (total)
Notas de crédito invertem débitos e créditos.

Saídas:
- "lancamentos": Excel genérico (uma folha por empresa), uma linha por movimento;
- "toconline":   Excel com os campos do modelo de importação do TOConline (um ficheiro por empresa);
- "modelo":      o modelo de importação do próprio programa (Sage, Primavera, PHC…), carregado pelo
                 gabinete, com as colunas mapeadas para os campos abaixo (um ficheiro por empresa).
"""
from __future__ import annotations

import io
import re
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..auth.servico import ErroAuth

CENTIMO = Decimal("0.01")
DEDUCAO = {"dedutivel": Decimal("1"), "dedutivel_50": Decimal("0.5")}

# ---------------------------------------------------------------- configuração por gabinete

CONFIG_PADRAO: dict = {
    "diario": "2",                       # código do diário de compras no programa
    "conta_fornecedor": "2211",          # fornecedores c/c
    "fornecedor_com_nif": False,         # conta do fornecedor = conta + NIF (ex.: 2211514873205)
    "contas_iva": {"normal": "2432", "intermedia": "2432", "reduzida": "2432"},
    "tipos_documento": {"FT": "FT", "FS": "FS", "FR": "FR", "NC": "NC", "ND": "ND", "VD": "VD", "EST": "FT", "OUTRO": "FT"},
    "descricao": "{fornecedor} {numero}",
}
TIPOS_TAXA_IVA = {"normal": "Normal", "intermedia": "Intermédia", "reduzida": "Reduzida"}


def config(guardada: dict | None) -> dict:
    """A configuração do gabinete completada com os valores por omissão."""
    c = {k: (dict(v) if isinstance(v, dict) else v) for k, v in CONFIG_PADRAO.items()}
    for k, v in (guardada or {}).items():
        if k in c and isinstance(c[k], dict) and isinstance(v, dict):
            c[k].update({kk: vv for kk, vv in v.items() if kk in c[k]})
        elif k in c:
            c[k] = v
    return c


def _conta(v, campo: str) -> str:
    v = re.sub(r"\s", "", str(v or ""))
    if not re.fullmatch(r"\d{1,20}", v):
        raise ErroAuth(422, "conta_invalida", "As contas só podem ter algarismos (ex.: 2432).", campo)
    return v


def validar_config(dados: dict) -> dict:
    c = config(dados)
    diario = str(c["diario"] or "").strip()
    if not diario or len(diario) > 20:
        raise ErroAuth(422, "diario_invalido", "Indique o código do diário de compras (até 20 caracteres).", "diario")
    descricao = str(c["descricao"] or "").strip()[:120] or CONFIG_PADRAO["descricao"]
    return {
        "diario": diario,
        "conta_fornecedor": _conta(c["conta_fornecedor"], "conta_fornecedor"),
        "fornecedor_com_nif": bool(c["fornecedor_com_nif"]),
        "contas_iva": {k: _conta(v, f"contas_iva.{k}") for k, v in c["contas_iva"].items()},
        "tipos_documento": {k: (str(v or k).strip()[:10] or k) for k, v in c["tipos_documento"].items()},
        "descricao": descricao,
    }


# ---------------------------------------------------------------- movimentos

CAMPOS: "OrderedDict[str, str]" = OrderedDict([
    ("n", "Número do lançamento"), ("diario", "Diário"), ("tipo_documento", "Tipo de documento"),
    ("data_lancamento", "Data do lançamento"), ("data_documento", "Data do documento"), ("descricao", "Descrição"),
    ("referencia", "Número do documento"), ("atcud", "ATCUD"), ("conta", "Conta"), ("debito", "Débito"),
    ("credito", "Crédito"), ("valor", "Valor (+ débito / − crédito)"), ("natureza", "Natureza (D/C)"),
    ("controlo_terceiros", "Controlo de terceiros"), ("nif_terceiro", "NIF do fornecedor"),
    ("nome_terceiro", "Nome do fornecedor"), ("base_iva", "Base do IVA"), ("taxa_iva", "Taxa do IVA"),
    ("codigo_iva", "Código de IVA (vazio)"), ("empresa_nif", "NIF da empresa"), ("empresa_nome", "Nome da empresa"),
])


@dataclass
class Movimento:
    n: int
    diario: str
    tipo_documento: str
    data_lancamento: date | None
    data_documento: date | None
    descricao: str
    referencia: str
    atcud: str
    conta: str
    debito: Decimal
    credito: Decimal
    controlo_terceiros: str
    nif_terceiro: str
    nome_terceiro: str
    base_iva: Decimal | None
    taxa_iva: Decimal | None
    empresa_nif: str
    empresa_nome: str

    @property
    def valor(self) -> Decimal:
        return self.debito - self.credito

    @property
    def natureza(self) -> str:
        return "D" if self.debito else "C"

    codigo_iva = ""

    def campo(self, nome: str):
        return getattr(self, nome)


def movimentos(faturas, d: dict, cfg: dict) -> "OrderedDict[str, list[Movimento]]":
    """Movimentos por empresa (chave: id da empresa), numerados 1, 2, … dentro de cada empresa."""
    por_empresa: "OrderedDict[str, list[Movimento]]" = OrderedDict()
    contadores: dict[str, int] = {}
    for f in faturas:
        e, fo = d["empresas"][f.empresa_id], d["forn"].get(f.fornecedor_id)
        chave = str(f.empresa_id)
        n = contadores[chave] = contadores.get(chave, 0) + 1
        nome_forn = fo.nome if fo else (f"NIF {f.nif_fornecedor}" if f.nif_fornecedor else "Fornecedor")
        nif = f.nif_fornecedor or ""
        desc = cfg["descricao"].replace("{fornecedor}", nome_forn).replace("{numero}", f.numero or "").replace(
            "{nif}", nif).strip()[:120]
        comum = dict(n=n, diario=cfg["diario"], tipo_documento=cfg["tipos_documento"].get(f.tipo_documento, f.tipo_documento),
                     data_lancamento=f.data_emissao, data_documento=f.data_emissao, descricao=desc,
                     referencia=f.numero or "", atcud=f.atcud or "", nif_terceiro=nif, nome_terceiro=nome_forn,
                     empresa_nif=e.nif, empresa_nome=e.nome)
        deducao = DEDUCAO.get(f.tratamento_iva, Decimal("0"))
        gasto, ivas = Decimal("0"), OrderedDict()
        for l in f.linhas_iva:
            ded = (l.iva * deducao).quantize(CENTIMO)
            gasto += l.base + (l.iva - ded)
            if ded:
                conta_iva = cfg["contas_iva"].get(l.tipo_taxa) or cfg["contas_iva"]["normal"]
                atual = ivas.get((conta_iva, l.taxa), (Decimal("0"), Decimal("0")))
                ivas[(conta_iva, l.taxa)] = (atual[0] + ded, atual[1] + l.base)
        if not f.linhas_iva:
            gasto = f.total
        nc = f.tipo_documento == "NC"

        def mov(conta, valor, base=None, taxa=None, terceiros=""):
            deb, cred = (valor, Decimal("0")) if not nc else (Decimal("0"), valor)
            return Movimento(conta=conta, debito=deb, credito=cred, base_iva=base, taxa_iva=taxa,
                             controlo_terceiros=terceiros, **comum)

        linhas = [mov(f.conta_codigo or "", gasto)]
        linhas += [mov(conta, v, base, taxa) for (conta, taxa), (v, base) in ivas.items()]
        total = sum((m.debito + m.credito for m in linhas), Decimal("0"))
        conta_forn = cfg["conta_fornecedor"] + (nif if cfg["fornecedor_com_nif"] and nif.isdigit() else "")
        fornecedor = mov(conta_forn, total, terceiros="Fornecedor")
        fornecedor.debito, fornecedor.credito = fornecedor.credito, fornecedor.debito  # o fornecedor fica do outro lado
        linhas.append(fornecedor)
        por_empresa.setdefault(chave, []).extend(linhas)
    return por_empresa


# ---------------------------------------------------------------- Excel

def _numero(v):
    return float(v) if isinstance(v, Decimal) else v


def _folha(ws, cab: list[str], linhas: list[list], larguras: dict[int, int] | None = None) -> None:
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    ws.append(cab)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4353E8")
    for l in linhas:
        ws.append([_numero(v) for v in l])
    for i, nome in enumerate(cab, 1):
        ws.column_dimensions[get_column_letter(i)].width = (larguras or {}).get(i, max(12, min(40, len(nome) + 4)))
        for c in ws.iter_rows(min_row=2, min_col=i, max_col=i):
            v = c[0].value
            if isinstance(v, date):
                c[0].number_format = "DD/MM/YYYY"
            elif isinstance(v, float):
                c[0].number_format = "#,##0.00"
    ws.freeze_panes = "A2"


def xlsx_generico(por_empresa: "OrderedDict[str, list[Movimento]]") -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)
    usados: set[str] = set()
    cab = ["Lançamento", "Diário", "Tipo doc.", "Data", "Documento", "ATCUD", "Descrição", "Conta", "Débito", "Crédito",
           "NIF fornecedor", "Fornecedor", "Base IVA", "Taxa IVA", "NIF empresa", "Empresa"]
    for movs in por_empresa.values():
        nome = re.sub(r"[\[\]:*?/\\]", "", movs[0].empresa_nome)[:28] or "Empresa"
        base, i = nome, 2
        while nome in usados:
            nome, i = f"{base[:25]} {i}", i + 1
        usados.add(nome)
        ws = wb.create_sheet(nome)
        _folha(ws, cab, [[m.n, m.diario, m.tipo_documento, m.data_lancamento, m.referencia, m.atcud, m.descricao, m.conta,
                          m.debito or None, m.credito or None, m.nif_terceiro, m.nome_terceiro, m.base_iva, m.taxa_iva,
                          m.empresa_nif, m.empresa_nome] for m in movs])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# Campos do modelo "Importação de lançamentos" do TOConline (Contabilidade > Configuração > Importação de
# lançamentos). Os nomes seguem a ajuda do TOConline; a ordem e os nomes das colunas de valores devem ser
# confirmados com o modelo descarregado da aplicação — se forem diferentes, use "Modelo do programa".
CAB_TOCONLINE = ["Número de ordem do lançamento", "Diário", "Tipo de Documento", "Data de lançamento", "Data de documento",
                 "Descrição", "Vossa referência", "Controlo de terceiros", "NIF do terceiro", "Nome do terceiro",
                 "Código da conta a movimentar", "Descrição do movimento", "Débito", "Crédito", "Código de IVA"]


def xlsx_toconline(movs: list[Movimento]) -> bytes:
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Lançamentos"
    _folha(ws, CAB_TOCONLINE, [[m.n, m.diario, m.tipo_documento, m.data_lancamento, m.data_documento, m.descricao,
                                m.referencia, m.controlo_terceiros or "Nenhum", m.nif_terceiro if m.controlo_terceiros else "",
                                m.nome_terceiro if m.controlo_terceiros else "", m.conta, m.descricao,
                                m.debito or None, m.credito or None, ""] for m in movs])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------- modelos carregados pelo gabinete

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9/ ]+", " ", s).strip()


# Primeira regra que encaixa no nome da coluna; cada campo só é sugerido uma vez.
SUGESTOES = [
    (r"\biva\b.*\bcod|\bcod.*\biva\b", "codigo_iva"), (r"\bbase\b|incidencia", "base_iva"), (r"\btaxa\b", "taxa_iva"),
    (r"\batcud\b", "atcud"), (r"nif.*(empresa|entidade propria)|contribuinte.*empresa", "empresa_nif"),
    (r"\bnif\b|contribuinte", "nif_terceiro"), (r"(nome|designacao).*(terceiro|fornecedor|entidade)|^fornecedor$|^entidade$", "nome_terceiro"),
    (r"controlo.*terceiro|tipo.*terceiro|^terceiro", "controlo_terceiros"), (r"diario", "diario"),
    (r"tipo.*doc|^doc.*tipo", "tipo_documento"), (r"data.*doc", "data_documento"), (r"^data|data.*(lanc|mov|contab)", "data_lancamento"),
    (r"refer|^no? .*doc|num.*doc|documento", "referencia"),
    (r"ordem|lancamento|^no?( |\.|$)|^num(ero)?( |$)|n.? mov", "n"), (r"descri|historico|observ", "descricao"),
    (r"\bdebito\b", "debito"), (r"\bcredito\b", "credito"), (r"natureza|^d/c$|sinal", "natureza"),
    (r"valor|montante|importancia|quantia", "valor"), (r"conta", "conta"),
]


def sugerir(cabecalhos: list[dict]) -> dict[str, str]:
    usados, out = set(), {}
    for c in cabecalhos:
        n = _norm(c["nome"])
        for rx, campo in SUGESTOES:
            if campo not in usados and re.search(rx, n):
                out[str(c["col"])] = campo
                usados.add(campo)
                break
    return out


def ler_modelo(dados: bytes) -> dict:
    """Lê o modelo (xlsx): folha, linha do cabeçalho e colunas."""
    from openpyxl import load_workbook
    if not dados.startswith(b"PK"):
        raise ErroAuth(422, "modelo_invalido", "O modelo tem de ser um ficheiro Excel .xlsx. Se for .xls, abra-o no Excel e grave como .xlsx.")
    try:
        wb = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
    except Exception:
        raise ErroAuth(422, "modelo_invalido", "Não foi possível abrir o ficheiro. Confirme que é um Excel .xlsx.")
    for ws in wb.worksheets:
        for i, linha in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), 1):
            nomes = [(j, str(v).strip()) for j, v in enumerate(linha, 1) if isinstance(v, str) and v.strip()]
            if len(nomes) >= 3:
                cab = [{"col": j, "nome": n[:80]} for j, n in nomes][:60]
                return {"folha": ws.title, "linha_cabecalho": i, "cabecalhos": cab}
    raise ErroAuth(422, "modelo_sem_cabecalho", "Não encontrámos uma linha de títulos das colunas nas primeiras 15 linhas do modelo.")


def validar_mapeamento(mapeamento: dict, cabecalhos: list[dict]) -> dict[str, str]:
    cols = {str(c["col"]) for c in cabecalhos}
    out = {str(k): v for k, v in (mapeamento or {}).items() if v}
    for k, v in out.items():
        if k not in cols:
            raise ErroAuth(422, "coluna_invalida", "O mapeamento refere uma coluna que não existe no modelo.")
        if v not in CAMPOS:
            raise ErroAuth(422, "campo_invalido", f"Campo desconhecido: {v}.")
    tem = set(out.values())
    if "conta" not in tem:
        raise ErroAuth(422, "falta_conta", "Indique em que coluna vai a conta.")
    if not ({"debito", "credito"} <= tem or "valor" in tem):
        raise ErroAuth(422, "falta_valor", "Indique as colunas de débito e crédito, ou uma coluna de valor.")
    return out


def xlsx_modelo(original: bytes, folha: str | None, linha_cabecalho: int, mapeamento: dict[str, str],
                movs: list[Movimento]) -> bytes:
    """Preenche o modelo do programa: apaga as linhas de exemplo e escreve os movimentos por baixo dos títulos."""
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(original))
    ws = wb[folha] if folha and folha in wb.sheetnames else wb.worksheets[0]
    if ws.max_row > linha_cabecalho:
        ws.delete_rows(linha_cabecalho + 1, ws.max_row - linha_cabecalho)
    for i, m in enumerate(movs, linha_cabecalho + 1):
        for col, campo in mapeamento.items():
            v = m.campo(campo)
            if isinstance(v, Decimal):
                v = float(v) if (v or campo in ("valor",)) else None
            c = ws.cell(row=i, column=int(col), value=v)
            if isinstance(v, date):
                c.number_format = "DD/MM/YYYY"
            elif isinstance(v, float):
                c.number_format = "0.00"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
