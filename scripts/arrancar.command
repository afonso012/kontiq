#!/bin/zsh -l
# ==========================================================================
#  Faturas em Dia — instala o que falta e arranca a plataforma no Mac.
#  Duplo clique no Finder. Pode correr-se várias vezes sem problema.
#  Tudo o que acontece fica também em scripts/arrancar.log
# ==========================================================================
set -u
cd "$(dirname "$0")/.."
RAIZ="$(pwd)"
LOG="$RAIZ/scripts/arrancar.log"
: > "$LOG"
exec > >(tee -a "$LOG") 2>&1

passo() { print -P "\n%F{green}▶ $1%f"; }
falha() { print -P "\n%F{red}✖ $1%f"; echo "ESTADO: FALHOU"; echo "Pode fechar esta janela."; exit 1; }

echo "Faturas em Dia — arranque $(date '+%d/%m/%Y %H:%M')  ($(sw_vers -productVersion) $(uname -m))"

# ---------- 1. Python 3.11+ ----------
passo "1/6 A procurar Python 3.11 ou mais recente"
PY=""
for c in python3.13 python3.12 python3.11 /opt/homebrew/bin/python3 python3; do
  if command -v $c >/dev/null 2>&1 && $c -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    PY=$(command -v $c); break
  fi
done
if [[ -z "$PY" ]]; then
  if command -v brew >/dev/null; then
    echo "A instalar Python 3.12 com o Homebrew…"; brew install python@3.12 || falha "Não consegui instalar o Python."
    PY=$(brew --prefix)/bin/python3.12
  else
    falha "Falta o Python 3.11+. Instale em https://www.python.org/downloads/ e volte a abrir este ficheiro."
  fi
fi
echo "Python: $PY ($($PY --version))"

# ---------- 2. PostgreSQL ----------
passo "2/6 A preparar a base de dados PostgreSQL"
MODO=""
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  MODO="docker"
  docker compose up -d postgres || falha "O Docker não conseguiu arrancar o PostgreSQL."
  echo -n "À espera do PostgreSQL"
  for i in {1..30}; do docker compose exec -T postgres pg_isready -U faturas -d faturas >/dev/null 2>&1 && break; echo -n "."; sleep 1; done; echo
elif command -v brew >/dev/null; then
  MODO="homebrew"
  if ! brew list --versions postgresql@16 >/dev/null; then
    echo "A instalar o PostgreSQL 16 com o Homebrew (pode demorar uns minutos)…"
    brew install postgresql@16 || falha "Não consegui instalar o PostgreSQL."
  fi
  export PATH="$(brew --prefix postgresql@16)/bin:$PATH"
  brew services start postgresql@16 >/dev/null 2>&1
  echo -n "À espera do PostgreSQL"
  for i in {1..30}; do pg_isready -h localhost -p 5432 >/dev/null 2>&1 && break; echo -n "."; sleep 1; done; echo
  pg_isready -h localhost -p 5432 >/dev/null 2>&1 || falha "O PostgreSQL não arrancou (porta 5432)."
  SQL='DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"'"'faturas'"'"') THEN CREATE ROLE faturas LOGIN PASSWORD '"'"'faturas'"'"' CREATEROLE; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='"'"'faturas_app'"'"') THEN CREATE ROLE faturas_app LOGIN PASSWORD '"'"'faturas_app'"'"'; END IF;
  END $$;'
  psql -h localhost -d postgres -v ON_ERROR_STOP=1 -c "$SQL" || falha "Não consegui criar os utilizadores da base de dados."
  if ! psql -h localhost -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='faturas'" | grep -q 1; then
    psql -h localhost -d postgres -c "CREATE DATABASE faturas OWNER faturas" || falha "Não consegui criar a base de dados."
  fi
  psql -h localhost -d faturas -c "ALTER SCHEMA public OWNER TO faturas; GRANT CONNECT ON DATABASE faturas TO faturas_app;" >/dev/null
else
  falha "Preciso do Docker Desktop (https://www.docker.com/products/docker-desktop/) ou do Homebrew (https://brew.sh) para a base de dados."
fi
echo "Base de dados pronta (via $MODO)."

# ---------- 3. Configuração ----------
passo "3/6 Configuração (.env)"
[[ -f .env ]] || cp .env.example .env
set -a; source .env; set +a
echo "OK"

# ---------- 4. Ambiente Python ----------
passo "4/6 A instalar as dependências Python (só demora da primeira vez)"
cd backend
[[ -d .venv ]] || $PY -m venv .venv || falha "Não consegui criar o ambiente Python."
source .venv/bin/activate
pip install -q --upgrade pip >/dev/null
pip install -q -e ".[dev]" || falha "A instalação das dependências falhou."
echo "OK"

# ---------- 5. Tabelas, dados e testes ----------
passo "5/6 A criar as tabelas, os dados de demonstração e a correr os testes"
alembic upgrade head || falha "As migrações falharam."
python -m app.demo >/dev/null || falha "Não consegui criar os dados de demonstração."
pytest -q || falha "Há testes a falhar."

# ---------- 6. API ----------
passo "6/6 A arrancar a API em http://localhost:8000"
lsof -ti tcp:8000 | xargs kill 2>/dev/null
(sleep 3; open "http://localhost:8000/docs") &
echo "ESTADO: A CORRER"
echo "Para parar: feche esta janela (ou Ctrl+C)."
uvicorn app.main:app --port 8000
