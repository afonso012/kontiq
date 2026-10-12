from datetime import date
from decimal import Decimal

import pytest

from app.domain.nif import nif_valido
from app.domain.qr_at import QRInvalido, ler_qr
from app.domain.validacao import validar


@pytest.mark.parametrize("nif", ["514873205", "516204874", "999999990", "PT 507 112 342", "503900125"])
def test_nif_validos(nif):
    assert nif_valido(nif)


@pytest.mark.parametrize("nif", ["514873209", "123456780", "12345678", "abc", "", None, "000000000"])
def test_nif_invalidos(nif):
    assert not nif_valido(nif)


QR = ("A:514873205*B:999999990*C:PT*D:FT*E:N*F:20261009*G:FT 2026/0457*H:JFR2M8KQ-457*"
      "I1:PT*I7:77.90*I8:17.92*N:17.92*O:95.82*Q:aB3x*R:2153")


def test_qr_simples():
    f = ler_qr(QR)
    assert f.nif_emitente == "514873205"
    assert f.tipo_documento == "FT"
    assert f.data_emissao == date(2026, 10, 9)
    assert f.numero == "FT 2026/0457"
    assert f.atcud == "JFR2M8KQ-457"
    assert f.total == Decimal("95.82")
    assert f.base_total == Decimal("77.90")
    assert f.iva_total == Decimal("17.92")
    [l] = f.linhas_iva
    assert (l.espaco_fiscal, l.tipo_taxa, l.taxa) == ("PT", "normal", Decimal("23.00"))


def test_qr_varias_taxas_e_madeira():
    qr = ("A:507112342*B:999999990*C:PT*D:FS*E:N*F:20261001*G:FS 1/9*H:ABC-9*"
          "I1:PT*I3:10.00*I4:0.60*I7:20.00*I8:4.60*K1:PT-MA*K7:10.00*K8:2.20*N:7.40*O:47.40")
    f = ler_qr(qr)
    assert [(l.espaco_fiscal, l.tipo_taxa) for l in f.linhas_iva] == [
        ("PT", "reduzida"), ("PT", "normal"), ("PT-MA", "normal")]
    assert f.base_total + f.iva_total == f.total


def test_qr_invalido():
    with pytest.raises(QRInvalido):
        ler_qr("https://exemplo.pt")


def test_validacoes():
    base = dict(pais_fornecedor="PT", nif_fornecedor="514873205", base_total=Decimal("77.90"),
                iva_total=Decimal("17.92"), total=Decimal("95.82"), data_emissao=date(2026, 10, 9),
                tipo_documento="FT", tratamento_iva="dedutivel", conta_codigo="6233")
    assert validar(**base) == []
    codigos = {p.codigo for p in validar(**{**base, "total": Decimal("90"), "nif_fornecedor": "514873209"})}
    assert codigos == {"contas_nao_batem", "nif_invalido"}
    est = {p.codigo for p in validar(**{**base, "pais_fornecedor": "IE", "nif_fornecedor": "IE6388047V"})}
    assert est == {"iva_estrangeiro"}
