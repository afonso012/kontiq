# Kontiq

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

**Forma mais simples:** no Finder, duplo clique em `scripts/arrancar.command`. Instala o que falta
(Python, PostgreSQL via Docker ou Homebrew), cria as tabelas e os dados de demonstração, corre os
testes e abre a API em http://localhost:8000/docs.

**Passo a passo (alternativa):**

```bash
git clone https://github.com/afonso012/kontiq.git && cd kontiq
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

## Aplicação web

O `arrancar.command` constrói a aplicação web (`frontend/`, React + Vite) e serve tudo em
**http://localhost:8000**. Os emails e SMS com códigos não saem do computador: aparecem no
**Mailpit**, em http://localhost:8025 (sem Mailpit, aparecem no terminal).

Contas de demonstração:

| Quem | Como entra |
|---|---|
| Contabilista | `demo@faturas.local` / `demonstracao-2026` |
| Cliente (portal) | telemóvel `912 345 678` ou `joaquim@faroleiro.local` → código no Mailpit |

Para mexer no frontend com recarregamento automático: `cd frontend && npm run dev`
(abre em http://localhost:5173 e fala com a API em :8000).

## Estado
- **Fase 0 (fundações):** modelo de dados, isolamento entre gabinetes por Row Level Security,
  dados base SNC, validação de NIF e leitura do QR da AT.
- **Autenticação:** registo do gabinete em 3 passos, confirmação do email por código, entrar e
  sair, repor a palavra-passe, portal do cliente sem palavra-passe (código por SMS ou email),
  sessões por cookie httpOnly, limites contra tentativas repetidas. 83 testes a passar.
- Próximo passo: painel de clientes (ver [roadmap](docs/04-roadmap.md)).
