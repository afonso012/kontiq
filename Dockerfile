# Imagem de produção da Kontiq: constrói a aplicação web e junta-a à API.
#   docker build -t kontiq .
# Usada pelo deploy/docker-compose.yml (ver docs/06-producao.md).

# 1) Aplicação web (React) → frontend/dist
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) API (Python) + ficheiros da aplicação web
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    AMBIENTE=producao PASTA_DOCUMENTOS=/dados/documentos
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install ".[producao]"
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY --from=web /web/dist /app/frontend/dist
RUN useradd --create-home --uid 1000 kontiq && mkdir -p /dados/documentos && chown -R kontiq /dados
USER kontiq
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=4).status == 200 else 1)"
# As migrações correm antes de arrancar (são idempotentes).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-2} --proxy-headers --forwarded-allow-ips='*'"]
