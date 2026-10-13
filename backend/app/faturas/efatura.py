"""Cruzamento com o e-Fatura.

No Portal das Finanças (e-Fatura › Adquirente › Verificar faturas › "Obter dados para Excel") a empresa
descarrega um CSV com as faturas de compra que os fornecedores comunicaram à AT. O gabinete carrega-o
aqui e a Kontiq compara com as faturas recebidas:

- em falta:      estão nas Finanças mas o cliente ainda não as enviou → pedir ao cliente;
- só na Kontiq:  recebidas, mas o fornecedor não as comunicou → o IVA pode não ser aceite como dedutível.

O formato do CSV não está documentado pela AT; a leitura reconhece as colunas pelos títulos, aceita
";" "," ou tabulações, UTF-8 ou Windows-1252, valores com "€" e separador de milhares, e o emitente
no formato "NIF - Nome".
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, false, func, select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..core.envio import enviar_email, enviar_sms
from ..empresas.servico import MESES, _url_portal, euros
from ..models import Empresa, Fatura, Fornecedor, Gabinete, LinhaEfatura, PedidoDocumentos, RegistoAtividade

MAX_BYTES = 2 * 1024 * 1024


def agora() -> datetime:
    return datetime.now(timezone.utc)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ ]+", " ", s)).strip()


def _num(n: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (n or "").upper())


def _valor(v: str | None) -> Decimal | None:
    s = (v or "").replace("€", "").replace(" ", "").replace(" ", "").strip()
    if not s or s in ("-", "—"):
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _data(v: str | None) -> date | None:
    s = (v or "").strip()[:10]
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


# Título da coluna (normalizado) → campo. A primeira regra que encaixa ganha.
COLUNAS = [
    (r"emitente|fornecedor|comerciante", "emitente"),
    (r"^nif|contribuinte", "nif"),
    (r"^nome|designacao", "nome"),
    (r"atcud", "numero"),  # "Nº Fatura / ATCUD"
    (r"fatura|n o doc|numero|documento", "numero"),
    (r"^tipo", "tipo"),
    (r"data", "data"),
    (r"base|incidencia|tributavel", "base"),
    (r"^iva|imposto", "iva"),
    (r"total|valor", "total"),
    (r"situacao|estado", "situacao"),
]


def _decodificar(dados: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            pass
    return dados.decode("latin-1")


def ler_csv(dados: bytes) -> list[dict]:
    if len(dados) > MAX_BYTES:
        raise ErroAuth(422, "ficheiro_grande", "O ficheiro tem mais de 2 MB. Exporte um mês de cada vez.")
    texto = _decodificar(dados)
    linhas_txt = [l for l in texto.splitlines() if l.strip()]
    if not linhas_txt:
        raise ErroAuth(422, "ficheiro_vazio", "O ficheiro está vazio.")
    amostra = "\n".join(linhas_txt[:5])
    sep = max([";", ",", "\t"], key=lambda c: amostra.count(c))
    linhas = list(csv.reader(io.StringIO("\n".join(linhas_txt)), delimiter=sep))
    for i, cab in enumerate(linhas[:6]):
        mapa: dict[str, int] = {}
        for j, nome in enumerate(cab):
            n = _norm(nome)
            for rx, campo in COLUNAS:
                if re.search(rx, n):
                    mapa.setdefault(campo, j)
                    break
        if "data" in mapa and "numero" in mapa and ("emitente" in mapa or "nif" in mapa):
            break
    else:
        raise ErroAuth(422, "formato_desconhecido",
                       "Este ficheiro não parece ser a exportação do e-Fatura. No Portal das Finanças use "
                       "\"Verificar faturas\" › \"Obter dados para Excel\" e carregue o ficheiro tal como foi descarregado.")
    out = []
    for l in linhas[i + 1:]:
        get = lambda campo: l[mapa[campo]].strip() if campo in mapa and mapa[campo] < len(l) else ""
        nif, nome = get("nif"), get("nome")
        if "emitente" in mapa:
            m = re.match(r"^\s*([A-Z]{0,2}\d{6,12})\s*[-–:]?\s*(.*)$", get("emitente"))
            nif, nome = (m.group(1), m.group(2).strip()) if m else (nif, get("emitente") or nome)
        numero, atcud = get("numero"), None
        if " / " in numero:  # "FT 2026/123 / JFR2M8KQ-123"
            numero, atcud = [x.strip() for x in numero.rsplit(" / ", 1)]
        d = _data(get("data"))
        if not (nif and numero and d):
            continue
        nif = nif.strip().upper() if nif[:2].isalpha() else re.sub(r"\D", "", nif)
        out.append({"nif": nif,
                    "nome": nome[:200] or None, "numero": numero[:120], "atcud": (atcud or None) and atcud[:120],
                    "tipo": get("tipo")[:40] or None, "data": d, "total": _valor(get("total")), "iva": _valor(get("iva")),
                    "base": _valor(get("base")), "situacao": get("situacao")[:60] or None})
    if not out:
        raise ErroAuth(422, "sem_faturas", "O ficheiro não tem faturas. Confirme o período escolhido no e-Fatura.")
    return out


def importar(s: Session, gabinete_id, utilizador_id, empresa_id, dados: bytes) -> dict:
    e = s.get(Empresa, empresa_id)
    if not e:
        raise ErroAuth(404, "nao_encontrada", "Empresa não encontrada.")
    linhas = [l for l in ler_csv(dados) if "anulad" not in _norm(l["situacao"] or "")]
    meses = sorted({l["data"].replace(day=1) for l in linhas})
    s.execute(delete(LinhaEfatura).where(LinhaEfatura.empresa_id == e.id, LinhaEfatura.periodo.in_(meses)))
    for l in linhas:
        s.add(LinhaEfatura(gabinete_id=gabinete_id, empresa_id=e.id, periodo=l["data"].replace(day=1),
                           nif_emitente=l["nif"], nome_emitente=l["nome"], numero=l["numero"], atcud=l["atcud"],
                           tipo=l["tipo"], data_emissao=l["data"], total=l["total"], iva=l["iva"], base=l["base"],
                           situacao=l["situacao"], importado_por=utilizador_id))
    s.flush()
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="empresa", entidade_id=e.id,
                           acao="efatura_importado", dados={"linhas": len(linhas), "meses": [m.isoformat() for m in meses]}))
    return {"linhas": len(linhas), "meses": [{"periodo": m.isoformat(), "periodo_txt": f"{MESES[m.month - 1]} de {m.year}",
                                              **_contagens(cruzar(s, e.id, m))} for m in meses]}


def _contagens(c: dict) -> dict:
    return {"em_falta": len(c["em_falta"]), "so_kontiq": len(c["so_kontiq"]), "ok": c["ok"]}


def cruzar(s: Session, empresa_id, mes: date) -> dict:
    mes = mes.replace(day=1)
    linhas = s.scalars(select(LinhaEfatura).where(LinhaEfatura.empresa_id == empresa_id, LinhaEfatura.periodo == mes)
                       .order_by(LinhaEfatura.data_emissao, LinhaEfatura.numero)).all()
    fim = (mes + timedelta(days=32)).replace(day=1)
    # Faturas do mês (pelo período ou pela data), mais as dos mesmos fornecedores em qualquer mês (ex.: entregue tarde).
    nifs = {l.nif_emitente for l in linhas}
    cand = s.execute(select(Fatura, Fornecedor.nome).outerjoin(Fornecedor, Fornecedor.id == Fatura.fornecedor_id).where(
        Fatura.empresa_id == empresa_id, Fatura.eliminada_em.is_(None), Fatura.estado != "rejeitada",
        (Fatura.periodo == mes) | ((Fatura.data_emissao >= mes) & (Fatura.data_emissao < fim)) |
        (Fatura.nif_fornecedor.in_(nifs) if nifs else false()))
        .order_by((Fatura.estado == "por_conferir").asc(), Fatura.criado_em, Fatura.id)).all()  # conferidas primeiro
    usadas: set = set()
    em_falta = []
    for l in linhas:
        alvo = None
        for f, _ in cand:
            if f.id in usadas or (f.nif_fornecedor or "") != l.nif_emitente:
                continue
            a, b = _num(f.numero), _num(l.numero)
            if (a and b and (a == b or a.endswith(b) or b.endswith(a))) or (l.atcud and f.atcud and _num(l.atcud) == _num(f.atcud)):
                alvo = f
                break
        if not alvo and l.total is not None:
            alvo = next((f for f, _ in cand if f.id not in usadas and f.nif_fornecedor == l.nif_emitente
                         and f.total == l.total and f.data_emissao == l.data_emissao), None)
        if alvo:
            usadas.add(alvo.id)
        else:
            em_falta.append({"id": str(l.id), "nif": l.nif_emitente, "fornecedor": l.nome_emitente, "numero": l.numero,
                             "tipo": l.tipo, "data": l.data_emissao.isoformat(),
                             "total": euros(l.total) if l.total is not None else None})
    so_kontiq = []
    if linhas:
        casadas = {(f.nif_fornecedor, _num(f.numero)) for f, _ in cand if f.id in usadas}
        for f, nome in cand:
            if f.id in usadas or f.periodo != mes or f.pais_fornecedor not in (None, "PT") or not f.nif_fornecedor:
                continue
            if (f.nif_fornecedor, _num(f.numero)) in casadas:  # cópia repetida de uma fatura que está no e-Fatura
                continue
            so_kontiq.append({"id": str(f.id), "nif": f.nif_fornecedor, "fornecedor": nome, "numero": f.numero,
                              "data": f.data_emissao.isoformat() if f.data_emissao else None, "total": euros(f.total)})
    importado = max((l.importado_em for l in linhas), default=None)
    return {"periodo": mes.isoformat(), "periodo_txt": f"{MESES[mes.month - 1]} de {mes.year}",
            "importado_em": importado.isoformat() if importado else None, "total_efatura": len(linhas),
            "em_falta": em_falta, "so_kontiq": so_kontiq, "ok": len(usadas),
            "so_kontiq_ids": [x["id"] for x in so_kontiq]}


def resumo_gabinete(s: Session, mes: date) -> list[dict]:
    """Por empresa com e-Fatura importado no mês: quantas faltam (para o painel)."""
    mes = mes.replace(day=1)
    ids = s.scalars(select(LinhaEfatura.empresa_id).where(LinhaEfatura.periodo == mes).distinct()).all()
    out = []
    for eid in ids:
        c = cruzar(s, eid, mes)
        if c["em_falta"]:
            out.append({"empresa_id": str(eid), "em_falta": len(c["em_falta"])})
    return out


def pedir_em_falta(s: Session, gabinete_id, utilizador_id, empresa_id, mes: date) -> dict:
    from ..subscricoes.servico import exigir_ativa
    exigir_ativa(s, gabinete_id)
    mes = mes.replace(day=1)
    e = s.get(Empresa, empresa_id)
    if not e:
        raise ErroAuth(404, "nao_encontrada", "Empresa não encontrada.")
    if not (e.telefone or e.email):
        raise ErroAuth(422, "contacto_sem_meio", "Esta empresa não tem telemóvel nem email. Edite-a primeiro.")
    faltam = cruzar(s, e.id, mes)["em_falta"]
    if not faltam:
        raise ErroAuth(409, "nada_em_falta", "Não falta nenhuma fatura do e-Fatura neste mês.")
    ultimo = s.scalar(select(func.max(PedidoDocumentos.enviado_em)).where(
        PedidoDocumentos.empresa_id == e.id, PedidoDocumentos.periodo == mes))
    if ultimo and (agora() - ultimo).total_seconds() < 3600:
        raise ErroAuth(429, "pedido_recente", "Já pediu faturas a esta empresa há menos de uma hora.")
    g = s.get(Gabinete, gabinete_id)
    nome = (e.contacto_nome or "").split()[0] if e.contacto_nome else ""
    lista = ", ".join(f"{x['fornecedor'] or 'NIF ' + x['nif']} ({x['numero']})" for x in faltam[:4])
    mais = f" e mais {len(faltam) - 4}" if len(faltam) > 4 else ""
    texto = (f"Olá{(' ' + nome) if nome else ''}. Nas Finanças aparecem {len(faltam)} "
             f"{'fatura' if len(faltam) == 1 else 'faturas'} de {MESES[mes.month - 1]} que o gabinete {g.nome} ainda não "
             f"recebeu: {lista}{mais}. Pode enviá-las em {_url_portal()}")
    canal = "sms" if e.telefone else "email"
    if canal == "sms":
        enviar_sms(e.telefone, texto)
    else:
        enviar_email(e.email, f"Faturas de {MESES[mes.month - 1]} em falta", "Faturas em falta", [texto])
    s.add(PedidoDocumentos(gabinete_id=gabinete_id, empresa_id=e.id, periodo=mes, mensagem=texto, canal=canal,
                           estado="enviado", criado_por=utilizador_id, enviado_em=agora()))
    return {"canal": canal, "faturas": len(faltam)}
