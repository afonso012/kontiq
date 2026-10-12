-- Corre uma vez, quando o volume da base de dados é criado.
-- Papel usado pela APLICAÇÃO: não é dono das tabelas, por isso fica sujeito
-- às políticas de Row Level Security (isolamento entre gabinetes).
CREATE ROLE faturas_app LOGIN PASSWORD 'faturas_app';
GRANT CONNECT ON DATABASE faturas TO faturas_app;
