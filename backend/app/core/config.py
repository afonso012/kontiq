"""Configuração lida das variáveis de ambiente (ficheiro .env em desenvolvimento)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    ambiente: str = "desenvolvimento"

    # A aplicação liga-se com um utilizador SEM privilégios (sujeito a RLS).
    database_url: str = "postgresql+psycopg://faturas_app:faturas_app@localhost:5432/faturas"
    # As migrações correm com o dono das tabelas.
    migrations_database_url: str = "postgresql+psycopg://faturas:faturas@localhost:5432/faturas"

    # Armazenamento de documentos (S3 compatível: MinIO em local, S3/R2 em produção).
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "documentos"
    s3_access_key: str = "faturas"
    s3_secret_key: str = "faturas-minio"

    # Domínio dos endereços de entrada por empresa (x7k2p9@entrada.exemplo.pt).
    dominio_email_entrada: str = "entrada.faturasemdia.local"

    secret_key: str = "mudar-em-producao"


@lru_cache
def get_settings() -> Settings:
    return Settings()
