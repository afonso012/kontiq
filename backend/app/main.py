"""Ponto de entrada da API (FastAPI). Os endpoints de negócio vêm nas próximas fases."""
from fastapi import FastAPI
from sqlalchemy import text

from .core.db import engine

app = FastAPI(title="Faturas em Dia", version="0.1.0")


@app.get("/saude")
def saude() -> dict:
    """Confirma que a API está viva e consegue falar com a base de dados."""
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    return {"estado": "ok"}
