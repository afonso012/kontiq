"""Palavras-passe, tokens de sessão e códigos de verificação.

- Palavras-passe: Argon2id (argon2-cffi), o algoritmo recomendado pela OWASP.
- Tokens de sessão e códigos: só guardamos um HMAC-SHA256 com a SECRET_KEY,
  nunca o valor em claro. Quem ler a base de dados não consegue usá-los.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import get_settings

_ph = PasswordHasher()

# Hash de referência para comparar quando o email não existe: o pedido demora o
# mesmo tempo e não revela se a conta existe.
_HASH_FALSO = _ph.hash("palavra-passe-que-nao-existe")

PASSWORD_MIN = 12
_COMUNS = {
    "123456789012", "password1234", "palavrapasse", "palavra-passe", "qwertyuiop12",
    "contabilidade", "faturas12345", "portugal1234", "benfica12345", "sporting1234",
}


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verificar_password(hash_guardado: str | None, password: str) -> bool:
    try:
        return _ph.verify(hash_guardado or _HASH_FALSO, password) and hash_guardado is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def problema_password(password: str, email: str = "", nome: str = "") -> str | None:
    """Devolve a razão pela qual a palavra-passe não serve, ou None se serve."""
    if len(password) < PASSWORD_MIN:
        return f"Use pelo menos {PASSWORD_MIN} caracteres."
    if len(password) > 200:
        return "Use no máximo 200 caracteres."
    baixo = password.lower()
    if baixo in _COMUNS or len(set(baixo)) < 5:
        return "Esta palavra-passe é demasiado fácil de adivinhar."
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in baixo:
        return "Não use o seu email na palavra-passe."
    for parte in nome.lower().split():
        if len(parte) >= 4 and parte in baixo:
            return "Não use o seu nome na palavra-passe."
    return None


def forca_password(password: str) -> int:
    """0 a 4, para o indicador do registo (o servidor só exige problema_password)."""
    if len(password) < PASSWORD_MIN:
        return 0 if len(password) < 8 else 1
    tipos = sum(bool(re.search(r, password)) for r in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    return min(4, 1 + (tipos >= 2) + (tipos >= 3) + (len(password) >= 16))


def _hmac(valor: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), valor.encode(), hashlib.sha256).hexdigest()


def novo_token() -> tuple[str, str]:
    """Token de sessão: (valor para o cookie, hash para a base de dados)."""
    token = secrets.token_urlsafe(32)
    return token, _hmac(token)


def hash_token(token: str) -> str:
    return _hmac(token)


def novo_codigo() -> tuple[str, str]:
    """Código de 6 dígitos: (valor para enviar, hash para guardar)."""
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    return codigo, _hmac("codigo:" + codigo)


def codigo_confere(codigo: str, codigo_hash: str) -> bool:
    return hmac.compare_digest(_hmac("codigo:" + codigo.strip()), codigo_hash)


_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def normalizar_email(email: str) -> str | None:
    email = (email or "").strip().lower()
    return email if len(email) <= 254 and _EMAIL.match(email) else None


def normalizar_telemovel(numero: str) -> str | None:
    """Telemóvel português em formato E.164 (+3519XXXXXXXX), ou None se não for válido."""
    digitos = re.sub(r"[\s\-().]", "", numero or "")
    if digitos.startswith("00"):
        digitos = "+" + digitos[2:]
    if digitos.startswith("+351"):
        digitos = digitos[4:]
    elif digitos.startswith("351") and len(digitos) == 12:
        digitos = digitos[3:]
    return "+351" + digitos if re.fullmatch(r"9[1236]\d{7}", digitos) else None
