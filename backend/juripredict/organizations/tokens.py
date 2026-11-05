"""Tokens de uso único para links enviados por e-mail.

Só o hash SHA-256 é gravado: quem ler o banco não consegue montar um link válido.
O token tem 256 bits de entropia, então um hash simples basta (não há senha
fraca para atacar por força bruta).
"""

import hashlib
import secrets


def gerar_token():
    return secrets.token_urlsafe(32)


def hash_token(token):
    return hashlib.sha256(str(token).encode()).hexdigest()
