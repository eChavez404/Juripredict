import base64
import hashlib
import hmac

from cryptography.fernet import Fernet
from django.conf import settings


def get_fernet():
    key = hashlib.sha256(settings.FIELD_ENCRYPTION_KEY.encode()).digest()
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
    return hmac.new(
        settings.FIELD_ENCRYPTION_KEY.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
