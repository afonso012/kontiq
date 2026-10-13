"""Os SMS saem no alfabeto GSM (160 caracteres por parte) e cabem numa parte com nomes realistas."""
from datetime import date
from decimal import Decimal

from app.core import envio
from app.core.envio import escolher_sms, partes_sms, texto_sms
from app.empresas.servico import MESES, euros


def test_letras_portuguesas_nao_obrigam_a_unicode():
    t = texto_sms("Olá João. Faltam faturas de março da Clínica Dentária Conceição — envie já… “obrigado”")
    assert t == 'Ola Joao. Faltam faturas de marco da Clinica Dentaria Conceicao - envie ja... "obrigado"'
    assert partes_sms(t) == 1


def test_euro_e_espacos_inquebraveis():
    t = texto_sms(f"Total {euros(Decimal('1955.72'))}")
    assert "?" not in t and t.endswith("€")


def test_partes():
    assert partes_sms("a" * 160) == 1
    assert partes_sms("a" * 161) == 2
    assert partes_sms("€" * 80) == 1 and partes_sms("€" * 81) == 2


def test_escolhe_a_versao_que_cabe_numa_parte():
    url = "https://kontiq.pt/portal"
    curta = f"Contabilidade Sado: faltam as faturas de setembro. Envie em {url}"
    longa = f"Olá Conceição. Contabilidade Sado & Associados: faltam as faturas de compras de setembro da empresa {'X' * 80}. Envie em {url}"
    assert escolher_sms(longa, curta) == curta
    assert escolher_sms(curta, longa) == curta
    assert escolher_sms(longa) == longa  # nenhuma cabe: fica a mais curta


def test_mensagens_reais_cabem_numa_parte():
    """Nomes compridos e com acentos, como na vida real: a primeira versão (com saudação) já cabe."""
    url, g, e, m = "https://kontiq.pt/portal", "Contabilidade Sado & Associados", "Restaurante O Faroleiro, Lda", MESES[8]
    for texto in (
        "Código de entrada no portal de faturas: 123456. Válido 15 minutos.",
        f"Olá Conceição. {g}: envie as faturas da empresa {e} pelo portal {url}",
        f"Olá Conceição. {g} tem uma pergunta sobre a fatura FT 2026/8120 ({euros(Decimal('1959.41'))}). Responda em {url}",
        f"Olá Conceição. {g}: faltam 12 faturas de {m} que já aparecem nas Finanças. Veja quais em {url}",
    ):
        assert partes_sms(texto_sms(texto)) == 1, (len(texto_sms(texto)), texto_sms(texto))


def test_enviar_sms_converte(monkeypatch):
    enviados = []
    monkeypatch.setattr(envio, "enviar_email", lambda para, assunto, titulo, linhas, **k: enviados.append(linhas[0]))
    envio.enviar_sms("+351912345678", "Olá, a sua dúvida está respondida.")
    assert enviados == ["Ola, a sua duvida esta respondida."]
