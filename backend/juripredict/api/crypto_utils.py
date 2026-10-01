import base64
import hashlib
import hmac

from cryptography.fernet import Fernet
from django.conf import settings


def get_fernet(secret: str | None = None) -> Fernet:
    """Cria uma instância Fernet a partir de um segredo sem expô-lo em logs."""
    key = hashlib.sha256((secret or settings.FIELD_ENCRYPTION_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_data(data: str) -> str:
    if not data:
        return data
    return get_fernet().encrypt(data.encode("utf-8")).decode("utf-8")


def decrypt_data(token: str) -> str:
    if not token:
        return token
    try:
        return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        # Mantém compatibilidade com registros legados ainda não criptografados.
        return token


def hash_data(data: str) -> str:
    return hash_data_with_key(data, settings.FIELD_ENCRYPTION_KEY)


def hash_data_with_key(data: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
