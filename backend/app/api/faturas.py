"""Faturas de uma empresa, conferência e documentos originais.

/api/empresas/{id}/faturas      lista do mês + números
/api/empresas/{id}/documentos   carregar PDFs e fotografias (multipart)
/api/faturas/{id}               ver, editar
/api/faturas/{id}/conferir|rejeitar|reabrir, /problemas/{pid}/resolver
/api/faturas/conferir-lote      várias de uma vez
/api/documentos/{id}            o ficheiro original (só do próprio gabinete)
/api/classificacao              categorias, contas SNC, tratamentos de IVA
"""
from __future__ import annotations

import uuid
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from ..auth.servico import ErroAuth
from ..core import armazenamento
from ..core.db import sessao_gabinete
from ..faturas import duvidas
from ..subscricoes.servico import exigir_ativa
from ..faturas import servico as svc
from .auth import SessaoAtual, exigir_gabinete
from .empresas import _mes

router = APIRouter(tags=["Faturas"])


def _no_gabinete(atual: SessaoAtual, fn):
    with sessao_gabinete(atual.gabinete_id) as s:
        return fn(s)


@router.get("/api/classificacao")
def classificacao(atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, svc.opcoes)


@router.get("/api/empresas/{empresa_id}/faturas")
def faturas_empresa(empresa_id: uuid.UUID, periodo: str | None = Query(None),
                    atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    mes = _mes(periodo)
    return _no_gabinete(atual, lambda s: svc.lista_empresa(s, empresa_id, mes))


@router.post("/api/empresas/{empresa_id}/documentos")
async def carregar(empresa_id: uuid.UUID, ficheiros: list[UploadFile] = File(...), periodo: str | None = Form(None),
                   atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Recebe PDFs e fotografias, guarda-os, lê o QR e cria as faturas por conferir."""
    if len(ficheiros) > svc.MAX_FICHEIROS:
        raise ErroAuth(422, "demasiados_ficheiros", f"Carregue no máximo {svc.MAX_FICHEIROS} ficheiros de cada vez.")
    lidos = []
    for f in ficheiros:
        dados = await f.read(svc.MAX_BYTES + 1)
        lidos.append((f.filename or "documento", dados))
    mes = _mes(periodo)

    def f(s):
        exigir_ativa(s, atual.gabinete_id)
        return svc.carregar(s, atual.gabinete_id, atual.utilizador_id, empresa_id, lidos, mes)
    res = _no_gabinete(atual, f)
    return {"resultados": [asdict(r) for r in res]}



@router.get("/api/faturas/{fatura_id}")
def ver(fatura_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: svc.detalhe(s, fatura_id))


class Linha(BaseModel):
    espaco: str | None = "PT"
    tipo_taxa: str | None = None
    taxa: float | None = None
    base: str | float | None = None
    iva: str | float | None = None


class DadosFatura(BaseModel):
    fornecedor: str | None = Field(default=None, max_length=200)
    nif: str | None = Field(default=None, max_length=30)
    pais: str | None = Field(default="PT", max_length=2)
    tipo_documento: str | None = None
    numero: str | None = Field(default=None, max_length=80)
    atcud: str | None = Field(default=None, max_length=80)
    data: str | None = None
    linhas: list[Linha] = Field(default_factory=list, max_length=20)
    total: str | float | None = None
    categoria_id: str | None = None
    conta: str | None = Field(default=None, max_length=12)
    tratamento_iva: str | None = None
    notas: str | None = Field(default=None, max_length=2000)


@router.put("/api/faturas/{fatura_id}")
def editar(fatura_id: uuid.UUID, corpo: DadosFatura, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    def f(s):
        svc.atualizar(s, atual.gabinete_id, atual.utilizador_id, fatura_id, corpo.model_dump())
        s.flush()
        return svc.detalhe(s, fatura_id)
    return _no_gabinete(atual, f)


class Conferir(BaseModel):
    lembrar: bool = False
    dados: DadosFatura | None = None


@router.post("/api/faturas/{fatura_id}/conferir")
def conferir(fatura_id: uuid.UUID, corpo: Conferir, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Grava as alterações (se vierem) e marca como conferida. Devolve a seguinte da fila."""
    def f(s):
        if corpo.dados:
            svc.atualizar(s, atual.gabinete_id, atual.utilizador_id, fatura_id, corpo.dados.model_dump())
            s.flush()
        fat = svc.conferir(s, atual.gabinete_id, atual.utilizador_id, fatura_id, corpo.lembrar)
        s.flush()
        d = svc.detalhe(s, fat.id)
        return {"seguinte": d["fila"]["seguinte"], "fatura": d}
    return _no_gabinete(atual, f)


class Lote(BaseModel):
    ids: list[uuid.UUID] = Field(max_length=200)


@router.post("/api/faturas/conferir-lote")
def conferir_lote(corpo: Lote, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Confere várias. As que não podem (erros ou sem classificação) ficam de fora, com o motivo."""
    feitas, falhadas = 0, []
    for fid in corpo.ids:
        try:
            _no_gabinete(atual, lambda s: svc.conferir(s, atual.gabinete_id, atual.utilizador_id, fid))
            feitas += 1
        except ErroAuth as e:
            falhadas.append({"id": str(fid), "mensagem": e.mensagem})
    return {"conferidas": feitas, "falhadas": falhadas}


class Rejeitar(BaseModel):
    motivo: str | None = Field(default=None, max_length=300)


@router.post("/api/faturas/{fatura_id}/rejeitar")
def rejeitar(fatura_id: uuid.UUID, corpo: Rejeitar, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    def f(s):
        svc.rejeitar(s, atual.utilizador_id, fatura_id, corpo.motivo)
        s.flush()
        return svc.detalhe(s, fatura_id)
    return _no_gabinete(atual, f)


@router.post("/api/faturas/{fatura_id}/reabrir")
def reabrir(fatura_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    def f(s):
        svc.reabrir(s, atual.utilizador_id, fatura_id)
        s.flush()
        return svc.detalhe(s, fatura_id)
    return _no_gabinete(atual, f)


@router.post("/api/faturas/{fatura_id}/problemas/{problema_id}/resolver")
def resolver(fatura_id: uuid.UUID, problema_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    def f(s):
        svc.resolver_problema(s, atual.utilizador_id, fatura_id, problema_id)
        s.flush()
        return svc.detalhe(s, fatura_id)
    return _no_gabinete(atual, f)


@router.get("/api/documentos/{documento_id}")
def ficheiro(documento_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)):
    """O ficheiro original. O RLS garante que só se abre um documento do próprio gabinete."""
    d = _no_gabinete(atual, lambda s: svc.documento(s, documento_id))
    caminho = armazenamento.caminho(d.chave_armazenamento)
    if not caminho.exists():
        raise ErroAuth(404, "ficheiro_em_falta", "O ficheiro original não está disponível.")
    cab = {"Cache-Control": "private, max-age=3600", "X-Frame-Options": "SAMEORIGIN"}
    if d.tipo_mime == "image/heic":
        # Os browsers (menos o Safari) não mostram HEIC: convertemos para JPEG ao abrir.
        import io
        import pillow_heif
        from PIL import Image, ImageOps
        pillow_heif.register_heif_opener()
        img = ImageOps.exif_transpose(Image.open(caminho)).convert("RGB")
        img.thumbnail((2400, 2400))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return Response(buf.getvalue(), media_type="image/jpeg", headers=cab)
    return FileResponse(caminho, media_type=d.tipo_mime, filename=d.nome_original, content_disposition_type="inline",
                        headers=cab)


@router.get("/api/documentos/{documento_id}/paginas")
def paginas(documento_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Quantas páginas tem o documento (as imagens têm uma)."""
    d = _no_gabinete(atual, lambda s: svc.documento(s, documento_id))
    if d.tipo_mime != "application/pdf":
        return {"paginas": 1}
    import pypdfium2 as pdfium
    return {"paginas": min(len(pdfium.PdfDocument(armazenamento.caminho(d.chave_armazenamento))), 20)}


@router.get("/api/documentos/{documento_id}/pagina/{n}")
def pagina(documento_id: uuid.UUID, n: int, atual: SessaoAtual = Depends(exigir_gabinete)):
    """Uma página do documento como imagem PNG, para ver em qualquer browser."""
    d = _no_gabinete(atual, lambda s: svc.documento(s, documento_id))
    return pagina_png(d, n)


def pagina_png(d, n: int) -> Response:
    caminho = armazenamento.caminho(d.chave_armazenamento)
    if not caminho.exists():
        raise ErroAuth(404, "ficheiro_em_falta", "O ficheiro original não está disponível.")
    import io
    if d.tipo_mime == "application/pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(caminho)
        if not 1 <= n <= min(len(pdf), 20):
            raise ErroAuth(404, "pagina_inexistente", "Página inexistente.")
        img = pdf[n - 1].render(scale=150 / 72).to_pil()
    else:
        if n != 1:
            raise ErroAuth(404, "pagina_inexistente", "Página inexistente.")
        from PIL import Image, ImageOps
        if d.tipo_mime == "image/heic":
            import pillow_heif
            pillow_heif.register_heif_opener()
        img = ImageOps.exif_transpose(Image.open(caminho)).convert("RGB")
        img.thumbnail((2000, 2000))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


# ---------------------------------------------------------------- dúvidas com o cliente

class Mensagem(BaseModel):
    texto: str = Field(max_length=2000)


@router.post("/api/faturas/{fatura_id}/duvida")
def perguntar(fatura_id: uuid.UUID, corpo: Mensagem, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    """Escreve ao cliente sobre esta fatura. Na primeira mensagem avisa-o por SMS ou email."""
    return _no_gabinete(atual, lambda s: duvidas.escrever_gabinete(s, atual.gabinete_id, atual.utilizador_id, fatura_id, corpo.texto))


@router.post("/api/faturas/{fatura_id}/duvida/resolver")
def resolver_duvida(fatura_id: uuid.UUID, atual: SessaoAtual = Depends(exigir_gabinete)) -> dict:
    return _no_gabinete(atual, lambda s: duvidas.resolver(s, atual.gabinete_id, atual.utilizador_id, fatura_id))
