"""Resumo semanal por email."""
from app import resumo
from tests.test_auth import cliente, enviados, limpar, nif_aleatorio, pytestmark  # noqa: F401
from tests.test_empresas import gabinete_confirmado
from tests.test_faturas import carregar, criar_empresa, imagem_com_qr, qr_texto


def test_resumo_preferencia_e_envio(cliente, enviados, limpar, monkeypatch):
    caixa = []
    monkeypatch.setattr(resumo, "enviar_email", lambda para, assunto, titulo, pars, codigo=None, html=None:
                        caixa.append({"para": para, "assunto": assunto, "html": html, "texto": pars}))
    email, _ = gabinete_confirmado(cliente, enviados, limpar)
    assert cliente.get("/api/resumo").json() == {"ativo": True, "enviado_em": None}

    eid, nif = criar_empresa(cliente)
    cliente.post("/api/empresas", json={"nif": nif_aleatorio(), "nome": "Sem Nada, Lda"})
    carregar(cliente, eid, ("a.pdf", imagem_com_qr(qr_texto(nif, "FT 1/1"), "PDF")))

    r = cliente.post("/api/resumo/enviar")
    assert r.status_code == 200 and r.json()["email"] == email
    m = caixa[-1]
    assert m["para"] == email and "conferido" in m["assunto"]
    assert "Kontiq" in m["html"] and "Abrir o painel" in m["html"] and "Sem Nada, Lda" in m["html"]
    assert any("documentos" in t for t in m["texto"])
    assert cliente.get("/api/resumo").json()["enviado_em"]
    html = cliente.get("/api/resumo/pre-visualizar")
    assert html.status_code == 200 and html.headers["content-type"].startswith("text/html")

    # O envio agendado não repete dentro de 6 dias e respeita quem desligou.
    antes = len(caixa)
    resumo.enviar_todos()
    assert not any(c["para"] == email for c in caixa[antes:])
    assert cliente.put("/api/resumo", json={"ativo": False}).json() == {"ativo": False}
    resumo.enviar_todos(forcar=True)
    assert not any(c["para"] == email for c in caixa[antes:])


def test_sem_nada_nao_envia():
    d = {"respostas": 0, "por_conferir": 0, "problemas": 0, "sem_faturas": [], "efatura": 0, "recebidos_semana": 0}
    assert resumo.ha_algo(d) is False
    assert resumo.ha_algo({**d, "sem_faturas": ["X"]}) is True
