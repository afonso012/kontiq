"""Configuração lida das variáveis de ambiente (ficheiro .env em desenvolvimento)."""
from functools import lru_cache
from pathlib import Path

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

    # Onde guardar os PDFs e fotografias. "local" = pasta no disco (desenvolvimento);
    # mais tarde "s3" para o armazenamento de objetos (MinIO/S3).
    armazenamento: str = "local"
    pasta_documentos: str = str(Path(__file__).resolve().parents[3] / "dados" / "documentos")

    # Domínio dos endereços de entrada por empresa (x7k2p9@entrada.exemplo.pt).
    dominio_email_entrada: str = "entrada.kontiq.pt"

    secret_key: str = "mudar-em-producao"

    # Leitura de faturas sem QR: "teste" (regras sobre o texto, sem custos),
    # "anthropic" (Claude, precisa de chave e tem custo por fatura) ou "desligada".
    ia_modo: str = "teste"
    anthropic_api_key: str = ""
    ia_modelo: str = "claude-haiku-5-5"

    # Endereço público da aplicação (links nos emails).
    url_publica: str = "http://localhost:8000"
    # Envio de email. Em desenvolvimento: Mailpit (caixa de correio de teste em http://localhost:8025).
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_utilizador: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False
    # Pagamentos da subscrição: "simulado" (página de teste, nunca em produção) ou "desligado".
    pagamentos_modo: str = "simulado"
    email_remetente: str = "Kontiq <nao-responder@kontiq.pt>"
    # SMS: em desenvolvimento não se envia nada; a mensagem aparece no Mailpit e no terminal.
    sms_modo: str = "simulado"

    @property
    def producao(self) -> bool:
        return self.ambiente == "producao"


@lru_cache
def get_settings() -> Settings:
    return Settings()
