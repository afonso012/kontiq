# Faturas em Dia

As faturas dos clientes, prontas para o programa de contabilidade do gabinete.

Plataforma para gabinetes de contabilidade em Portugal: recolhe as faturas de
compras das empresas-cliente, lê-as (código QR da AT ou IA), valida, classifica
(conta SNC e IVA, com memória por fornecedor) e entrega-as organizadas.

📄 Documentação em [`docs/`](docs/): [visão](docs/01-visao.md) ·
[arquitetura](docs/02-arquitetura.md) · [modelo de dados](docs/03-modelo-de-dados.md) ·
[roadmap](docs/04-roadmap.md)

## Pré-requisitos (Mac)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (para a base de dados e o armazenamento)
- Python 3.11 ou mais recente (`brew install python@3.12`)

## Arrancar em local

```bash
cd ~/Projetos/faturas-em-dia
cp .env.example .env

# 1. Base de dados e armazenamento
docker compose up -d

# 2. Ambiente Python
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Criar as tabelas, dados base e regras de isolamento
alembic upgrade head

# 4. Testes (os de base de dados usam as variáveis do .env)
set -a; source ../.env; set +a
pytest

# 5. API
uvicorn app.main:app --reload
# → http://localhost:8000/saude   e   http://localhost:8000/docs
```

## Estado
Fase 0 (fundações) concluída: modelo de dados com 20 tabelas, isolamento entre
gabinetes por Row Level Security, dados base SNC, validação de NIF e leitura do
QR da AT — 23 testes a passar. Próximo passo: autenticação e API do gabinete
(ver [roadmap](docs/04-roadmap.md)).
