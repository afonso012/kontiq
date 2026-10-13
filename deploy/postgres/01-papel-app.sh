#!/bin/sh
# Corre uma vez, quando o volume da base de dados é criado.
# Papel usado pela APLICAÇÃO: não é dono das tabelas, por isso fica sujeito às políticas
# de Row Level Security (isolamento entre gabinetes). A palavra-passe vem de APP_DB_PASSWORD.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE faturas_app LOGIN PASSWORD '${APP_DB_PASSWORD}';
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO faturas_app;
SQL
