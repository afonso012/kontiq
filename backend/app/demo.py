"""Dados de demonstração: um gabinete fictício com empresas e faturas.

Corre com `python -m app.demo`. É idempotente: se o gabinete demo já existir,
não cria nada de novo. Usa o papel da aplicação, por isso passa pelo RLS.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from .core.db import sessao_gabinete, sessao_sem_gabinete
from .core.seguranca import hash_password
from .domain.qr_at import ler_qr
from .domain.validacao import validar
from .models import (
    AcessoPortal, Categoria, Empresa, Fatura, Fornecedor, Gabinete, LinhaIVA, MembroGabinete,
    ProblemaFatura, RegraFornecedor, Utilizador,
)

NIF_GABINETE_DEMO = "502877642"

# Contas de demonstração (só em desenvolvimento).
DEMO_CONTABILISTA = ("Marta Ferreira", "demo@faturas.local", "demonstracao-2026")
DEMO_CLIENTE = ("Joaquim Faroleiro", "joaquim@faroleiro.local", "+351912345678")

EMPRESAS = [
    ("Restaurante O Faroleiro, Lda", "512173850", "Sr. Joaquim"),
    ("Oficina Digital do Sado, Lda", "516204874", "Marta"),
    ("Clínica Dentária Bonfim", "508973856", "Dra. Inês"),
]

# (empresa, fornecedor, categoria, texto do QR) — QR no formato da AT.
FATURAS_QR = [
    (0, "Distribuidora Alimentar do Sado, SA", "Mercadorias",
     "A:516273850*B:512173850*C:PT*D:FT*E:N*F:20260908*G:FT 2026/7712*H:MW3P8TQA-7712*I1:PT*I3:812.40*I4:48.74*N:48.74*O:861.14"),
    (0, "Distribuidora Alimentar do Sado, SA", "Mercadorias",
     "A:516273850*B:512173850*C:PT*D:FT*E:N*F:20261006*G:FT 2026/8120*H:MW3P8TQA-8120*I1:PT*I3:905.10*I4:54.31*N:54.31*O:959.41"),
    (0, "Telecomunicações do Sado, SA", "Comunicações",
     "A:503900125*B:512173850*C:PT*D:FT*E:N*F:20261012*G:FT 2026/94011*H:K9WQ2LMB-94011*I1:PT*I7:30.00*I8:6.90*N:6.90*O:36.90"),
    (1, "Papelaria e Escritório Sado, Lda", "Material de escritório",
     "A:514873205*B:516204874*C:PT*D:FT*E:N*F:20261009*G:FT 2026/0457*H:JFR2M8KQ-457*I1:PT*I7:77.90*I8:17.92*N:17.92*O:95.82"),
    (1, "Posto de Abastecimento da Moita", "Combustível",
     "A:509871224*B:516204874*C:PT*D:FS*E:N*F:20261006*G:FS 01/31877*H:PX7Q1NNA-31877*I1:PT*I7:48.78*I8:11.22*N:11.22*O:60.00"),
    (2, "Dentalmed Distribuição, SA", "Mercadorias",
     "A:506188337*B:508973856*C:PT*D:FT*E:N*F:20261009*G:FT DM/41502*H:DM5R7TXA-41502*I1:PT*I7:288.50*I8:66.36*N:66.36*O:354.86"),
]


def semear() -> str:
    gid = _semear_gabinete()
    _semear_contas(gid)
    _contacto_faroleiro(gid)
    return gid


def _contacto_faroleiro(gid) -> None:
    """O contacto do Faroleiro é o cliente de demonstração do portal."""
    nome, email, tel = DEMO_CLIENTE
    with sessao_gabinete(gid) as s:
        e = s.scalar(select(Empresa).where(Empresa.nif == EMPRESAS[0][1]))
        if e and not e.telefone:
            e.contacto_nome, e.telefone, e.email = nome, tel, email


def _semear_contas(gid) -> None:
    """Contabilista (entra com email e palavra-passe) e cliente do portal (entra por código)."""
    from datetime import datetime, timezone
    agora = datetime.now(timezone.utc)
    with sessao_sem_gabinete() as s:
        nome, email, password = DEMO_CONTABILISTA
        u = s.scalar(select(Utilizador).where(Utilizador.email == email))
        if not u:
            u = Utilizador(nome=nome, email=email, password_hash=hash_password(password), email_confirmado_em=agora)
            s.add(u); s.flush()
            s.add(MembroGabinete(gabinete_id=gid, utilizador_id=u.id, papel="dono"))
        nome, email, tel = DEMO_CLIENTE
        c = s.scalar(select(Utilizador).where(Utilizador.email == email))
        if not c:
            c = Utilizador(nome=nome, email=email, telefone=tel, email_confirmado_em=agora)
            s.add(c); s.flush()
            with sessao_gabinete(gid) as sg:  # empresas têm RLS: ler dentro do gabinete
                empresa_id = sg.scalar(select(Empresa.id).where(Empresa.nif == EMPRESAS[0][1]))
            s.add(AcessoPortal(gabinete_id=gid, empresa_id=empresa_id, utilizador_id=c.id, papel="gestor"))


def _semear_gabinete() -> str:
    with sessao_sem_gabinete() as s:
        g = s.scalar(select(Gabinete).where(Gabinete.nif == NIF_GABINETE_DEMO))
        if g:
            return str(g.id)
        g = Gabinete(nome="Contabilidade Sado (demo)", nif=NIF_GABINETE_DEMO, plano="gabinete",
                     programa_contabilidade="toconline", dimensao="21_50")
        s.add(g); s.flush()
        gid = g.id

    with sessao_gabinete(gid) as s:
        empresas = []
        for nome, nif, contacto in EMPRESAS:
            e = Empresa(gabinete_id=gid, nome=nome, nif=nif, contacto_nome=contacto)
            s.add(e); empresas.append(e)
        s.flush()
        cats = {c.nome: c for c in s.scalars(select(Categoria))}
        fornecedores: dict[str, Fornecedor] = {}
        vistos: set[tuple] = set()
        for idx, nome_forn, cat_nome, texto in FATURAS_QR:
            q = ler_qr(texto)
            emp, cat = empresas[idx], cats[cat_nome]
            forn = fornecedores.get(q.nif_emitente)
            if not forn:
                forn = Fornecedor(gabinete_id=gid, nif=q.nif_emitente, nome=nome_forn)
                s.add(forn); s.flush(); fornecedores[q.nif_emitente] = forn
                s.add(RegraFornecedor(gabinete_id=gid, fornecedor_id=forn.id, categoria_id=cat.id,
                                      conta_codigo=cat.conta_codigo, tratamento_iva=cat.tratamento_iva))
            f = Fatura(
                gabinete_id=gid, empresa_id=emp.id, fornecedor_id=forn.id,
                periodo=q.data_emissao.replace(day=1), tipo_documento=q.tipo_documento, numero=q.numero,
                atcud=q.atcud, data_emissao=q.data_emissao, nif_fornecedor=q.nif_emitente,
                nif_adquirente=q.nif_adquirente, base_total=q.base_total, iva_total=q.iva_total, total=q.total,
                metodo_leitura="qr", qr_texto=texto, categoria_id=cat.id, conta_codigo=cat.conta_codigo,
                tratamento_iva=cat.tratamento_iva, origem_classificacao="regra", estado="conferida",
            )
            for l in q.linhas_iva:
                f.linhas_iva.append(LinhaIVA(gabinete_id=gid, espaco_fiscal=l.espaco_fiscal, tipo_taxa=l.tipo_taxa,
                                             taxa=l.taxa, base=l.base, iva=l.iva))
            for p in validar(pais_fornecedor="PT", nif_fornecedor=q.nif_emitente, base_total=q.base_total,
                             iva_total=q.iva_total, total=q.total, data_emissao=q.data_emissao,
                             tipo_documento=q.tipo_documento, tratamento_iva=cat.tratamento_iva,
                             conta_codigo=cat.conta_codigo):
                f.problemas.append(ProblemaFatura(gabinete_id=gid, codigo=p.codigo, nivel=p.nivel, mensagem=p.mensagem))
            s.add(f)
            vistos.add((emp.id, q.nif_emitente, q.numero))

        # Um duplicado de propósito, para se ver a deteção a funcionar.
        _, nome_forn, cat_nome, texto = FATURAS_QR[1]
        q, emp, cat = ler_qr(texto), empresas[0], cats[cat_nome]
        dup = Fatura(gabinete_id=gid, empresa_id=emp.id, fornecedor_id=fornecedores[q.nif_emitente].id,
                     periodo=date(2026, 10, 1), tipo_documento="FT", numero=q.numero, atcud=q.atcud,
                     data_emissao=q.data_emissao, nif_fornecedor=q.nif_emitente, base_total=q.base_total,
                     iva_total=q.iva_total, total=q.total, metodo_leitura="qr", qr_texto=texto,
                     categoria_id=cat.id, conta_codigo=cat.conta_codigo, tratamento_iva=cat.tratamento_iva,
                     origem_classificacao="regra", notas="Recebida outra vez por WhatsApp")
        dup.problemas.append(ProblemaFatura(gabinete_id=gid, codigo="duplicado", nivel="erro",
                                            mensagem=f"Possível duplicado de {q.numero}."))
        s.add(dup)
    return str(gid)


if __name__ == "__main__":
    print(semear())
