"""Configuração dos lançamentos e modelos de importação dos programas, por gabinete."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.servico import ErroAuth
from ..core import armazenamento
from ..models import Gabinete, MembroGabinete, ModeloExportacao, RegistoAtividade
from . import lancamentos as L
from .servico import PROGRAMAS

MAX_MODELO = 5 * 1024 * 1024


def _exigir_gestor(s: Session, gabinete_id, utilizador_id) -> None:
    papel = s.scalar(select(MembroGabinete.papel).where(MembroGabinete.gabinete_id == gabinete_id,
                                                        MembroGabinete.utilizador_id == utilizador_id))
    if papel not in ("dono", "admin"):
        raise ErroAuth(403, "sem_permissao", "Só o dono ou um administrador pode mudar a configuração das exportações.")


def ver_config(s: Session, gabinete_id) -> dict:
    g = s.get(Gabinete, gabinete_id)
    return {"config": L.config(g.config_exportacao), "padrao": L.CONFIG_PADRAO, "tipos_taxa": L.TIPOS_TAXA_IVA,
            "campos": [{"id": k, "nome": v} for k, v in L.CAMPOS.items()],
            "programas": [{"id": k, "nome": v} for k, v in PROGRAMAS.items()]}


def gravar_config(s: Session, gabinete_id, utilizador_id, dados: dict) -> dict:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    g = s.get(Gabinete, gabinete_id)
    g.config_exportacao = L.validar_config(dados)
    s.add(RegistoAtividade(gabinete_id=gabinete_id, utilizador_id=utilizador_id, entidade="exportacao",
                           acao="configuracao", dados=g.config_exportacao))
    return ver_config(s, gabinete_id)


def _json(m: ModeloExportacao) -> dict:
    return {"id": str(m.id), "nome": m.nome, "programa": m.programa, "programa_nome": PROGRAMAS[m.programa],
            "folha": m.folha, "linha_cabecalho": m.linha_cabecalho, "cabecalhos": m.cabecalhos,
            "mapeamento": m.mapeamento, "criado_em": m.criado_em.isoformat() if m.criado_em else None}


def listar(s: Session) -> list[dict]:
    return [_json(m) for m in s.scalars(select(ModeloExportacao).order_by(ModeloExportacao.criado_em))]


def carregar(s: Session, gabinete_id, utilizador_id, nome_ficheiro: str, dados: bytes, programa: str, nome: str | None) -> dict:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    if programa not in PROGRAMAS:
        raise ErroAuth(422, "programa_invalido", "Escolha o programa de contabilidade.", "programa")
    if len(dados) > MAX_MODELO:
        raise ErroAuth(422, "modelo_grande", "O modelo tem mais de 5 MB. Grave uma cópia só com a linha dos títulos.")
    lido = L.ler_modelo(dados)
    mid = uuid.uuid4()
    chave = f"{gabinete_id}/modelos/{mid}.xlsx"
    armazenamento.guardar(chave, dados)
    base = nome_ficheiro.rsplit(".", 1)[0].replace("_", " ").strip()[:50]
    nome = (nome or "").strip()[:80] or (f"{PROGRAMAS[programa]} ({base})" if PROGRAMAS[programa].lower() not in base.lower() else base)
    m = ModeloExportacao(id=mid, gabinete_id=gabinete_id, nome=nome, programa=programa, folha=lido["folha"],
                         linha_cabecalho=lido["linha_cabecalho"], cabecalhos=lido["cabecalhos"], mapeamento={},
                         chave_armazenamento=chave, criado_por=utilizador_id)
    s.add(m)
    s.flush()
    return {**_json(m), "sugestao": L.sugerir(lido["cabecalhos"])}


def atualizar(s: Session, gabinete_id, utilizador_id, modelo_id, nome: str | None, programa: str | None, mapeamento: dict) -> dict:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    m = s.get(ModeloExportacao, modelo_id)
    if not m:
        raise ErroAuth(404, "nao_encontrado", "Modelo não encontrado.")
    if programa:
        if programa not in PROGRAMAS:
            raise ErroAuth(422, "programa_invalido", "Escolha o programa de contabilidade.", "programa")
        m.programa = programa
    if nome and nome.strip():
        m.nome = nome.strip()[:80]
    m.mapeamento = L.validar_mapeamento(mapeamento, m.cabecalhos)
    return _json(m)


def apagar(s: Session, gabinete_id, utilizador_id, modelo_id) -> None:
    _exigir_gestor(s, gabinete_id, utilizador_id)
    m = s.get(ModeloExportacao, modelo_id)
    if not m:
        raise ErroAuth(404, "nao_encontrado", "Modelo não encontrado.")
    s.delete(m)
