"""Validações de uma fatura que não precisam da base de dados.

A deteção de duplicados precisa de consultar outras faturas e vive no serviço.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .nif import nif_valido

TOLERANCIA = Decimal("0.02")


@dataclass(frozen=True)
class Problema:
    codigo: str
    nivel: str  # "erro" | "aviso"
    mensagem: str


def validar(
    *,
    pais_fornecedor: str,
    nif_fornecedor: str | None,
    base_total: Decimal,
    iva_total: Decimal,
    total: Decimal,
    data_emissao: object | None,
    tipo_documento: str,
    tratamento_iva: str,
    conta_codigo: str | None,
) -> list[Problema]:
    p: list[Problema] = []
    pais = (pais_fornecedor or "PT").upper()

    if data_emissao is None:
        p.append(Problema("sem_data", "erro", "Falta a data da fatura."))
    if total <= 0 and tipo_documento != "NC":
        p.append(Problema("sem_total", "erro", "Falta o total da fatura."))
    if total > 0 and abs(base_total + iva_total - total) > TOLERANCIA:
        p.append(Problema("contas_nao_batem", "erro",
                          f"Base + IVA ({base_total + iva_total:.2f} €) não bate com o total ({total:.2f} €)."))
    if pais == "PT":
        if not nif_fornecedor:
            p.append(Problema("sem_nif", "aviso", "Falta o NIF do fornecedor."))
        elif not nif_valido(nif_fornecedor):
            p.append(Problema("nif_invalido", "erro", f"O NIF {nif_fornecedor} não é um NIF português válido."))
    elif iva_total > 0:
        p.append(Problema("iva_estrangeiro", "aviso",
                          "Fornecedor estrangeiro com IVA: confirme se devia ser autoliquidação."))
    if not conta_codigo or tratamento_iva == "por_definir":
        p.append(Problema("sem_classificacao", "aviso", "Classificação por definir (conta SNC ou tratamento do IVA)."))
    return p
