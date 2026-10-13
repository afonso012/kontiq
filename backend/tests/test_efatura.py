"""Cruzamento com o CSV do e-Fatura."""
import pytest

from app.faturas import efatura as ef
from tests.test_auth import cliente, enviados, limpar, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado, mensagens, telemovel  # noqa: F401
from tests.test_auth import nif_aleatorio
from tests.test_faturas import DATA, MES, carregar, imagem_com_qr, qr_texto

D = f"{DATA[6:8]}/{DATA[4:6]}/{DATA[:4]}"  # dd/mm/aaaa


def _csv(linhas: list[str]) -> bytes:
    cab = "Setor;Emitente;Nº Fatura / ATCUD;Tipo;Data Emissão;Total;IVA;Base Tributável;Situação"
    return ("\r\n".join([cab, *linhas]) + "\r\n").encode("cp1252")


@pytest.fixture
def avisos(monkeypatch):
    caixa = []
    monkeypatch.setattr(ef, "enviar_sms", lambda n, t: caixa.append(t))
    monkeypatch.setattr(ef, "enviar_email", lambda *a, **k: caixa.append(a))
    return caixa


def test_ler_csv_variantes():
    l = ef.ler_csv(_csv([f"Outros;514873205 - Papelaria Sado, Lda;FT 5/1 / JFR2M8KQ-1;Fatura;{D};€ 1.095,82;€ 17,92;€ 1.077,90;Registado"]))
    assert l[0]["nif"] == "514873205" and l[0]["nome"] == "Papelaria Sado, Lda" and l[0]["numero"] == "FT 5/1"
    assert l[0]["atcud"] == "JFR2M8KQ-1" and str(l[0]["total"]) == "1095.82" and str(l[0]["base"]) == "1077.90"
    utf = ("NIF Emitente,Nome Emitente,Número Documento,Data,Total\n"
           f"514873205,Papelaria,FT 9,{DATA[:4]}-{DATA[4:6]}-{DATA[6:8]},12.30\n").encode()
    l2 = ef.ler_csv(utf)
    assert l2[0]["nif"] == "514873205" and l2[0]["numero"] == "FT 9" and str(l2[0]["total"]) == "12.30"
    with pytest.raises(Exception) as e:
        ef.ler_csv(b"isto,nao,e\n1,2,3\n")
    assert "e-Fatura" in str(e.value.mensagem)


def test_cruzar_pedir_e_painel(cliente, enviados, limpar, mensagens, avisos):
    gabinete_confirmado(cliente, enviados, limpar)
    tel = telemovel()
    limpar[0].append(f"351{tel}@telemovel.local")
    nif = nif_aleatorio()
    eid = cliente.post("/api/empresas", json={"nif": nif, "nome": "Cruzada, Lda", "contacto_nome": "Rui", "telefone": tel}).json()["id"]
    carregar(cliente, eid, ("a.pdf", imagem_com_qr(qr_texto(nif, "FT 5/1"), "PDF")),
             ("b.pdf", imagem_com_qr(qr_texto(nif, "FT 5/2"), "PDF")))

    csv = _csv([f"Outros;514873205 - Papelaria Sado, Lda;FT 5/1 / JFR2M8KQ-1;Fatura;{D};€ 95,82;€ 17,92;€ 77,90;Registado",
                f"Outros;509871224 - Posto da Moita;FS 01/31877 / AAA-9;Fatura simplificada;{D};€ 60,00;€ 11,22;€ 48,78;Registado",
                f"Outros;503900125 - Telecom;FT 2026/1 / BBB-1;Fatura;{D};€ 36,90;€ 6,90;€ 30,00;Anulado"])
    r = cliente.post(f"/api/empresas/{eid}/efatura", files={"ficheiro": ("faturas.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["linhas"] == 2 and r.json()["meses"][0] | {} and r.json()["meses"][0]["em_falta"] == 1

    c = cliente.get(f"/api/empresas/{eid}/efatura", params={"periodo": MES}).json()
    assert c["ok"] == 1 and c["total_efatura"] == 2
    assert [x["numero"] for x in c["em_falta"]] == ["FS 01/31877"] and c["em_falta"][0]["fornecedor"] == "Posto da Moita"
    assert [x["numero"] for x in c["so_kontiq"]] == ["FT 5/2"]

    lista = cliente.get(f"/api/empresas/{eid}/faturas", params={"periodo": MES}).json()
    assert lista["efatura"]["em_falta"] == 1
    assert {f["numero"]: f["fora_efatura"] for f in lista["faturas"]} == {"FT 5/1": False, "FT 5/2": True}
    item = next(a for a in cliente.get("/api/painel", params={"periodo": MES}).json()["atencao"] if a["codigo"] == "efatura_em_falta")
    assert item["empresa_id"] == eid and item["titulo"] == "Falta 1 fatura"

    p = cliente.post(f"/api/empresas/{eid}/efatura/pedir", json={"periodo": MES})
    assert p.status_code == 200 and p.json() == {"canal": "sms", "faturas": 1}
    assert "falta 1 fatura de" in avisos[-1] and "já aparece nas Finanças. Veja qual" in avisos[-1]
    assert cliente.post(f"/api/empresas/{eid}/efatura/pedir", json={"periodo": MES}).status_code == 429

    # O cliente envia a que faltava: deixa de estar em falta. Reimportar substitui o mês.
    carregar(cliente, eid, ("c.pdf", imagem_com_qr(qr_texto(nif, "FS 01/31877", nif_forn="509871224", total="60.00"), "PDF")))
    assert cliente.get(f"/api/empresas/{eid}/efatura", params={"periodo": MES}).json()["em_falta"] == []
    cliente.post(f"/api/empresas/{eid}/efatura", files={"ficheiro": ("f.csv", csv, "text/csv")})
    assert cliente.get(f"/api/empresas/{eid}/efatura", params={"periodo": MES}).json()["total_efatura"] == 2
    assert cliente.post(f"/api/empresas/{eid}/efatura", files={"ficheiro": ("x.csv", b"ola\n", "text/csv")}).status_code == 422
