"""Remoção de dados pessoais com formato conhecido antes de qualquer envio a terceiros."""

import re

# O número CNJ do processo não casa com nenhum deles e é preservado.
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_PIS = re.compile(r"\b\d{3}\.\d{5}\.\d{2}-\d\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Exige o DDD: sem ele, um intervalo de anos (2019-2024) pareceria telefone.
_PHONE = re.compile(r"(?:\(\d{2}\)\s?|\b\d{2}\s)9?\d{4}-?\d{4}\b")


def mask_documents(text: str) -> str:
    """Troca documentos e contatos por marcadores. Nomes não são cobertos."""
    for pattern, marker in (
        (_EMAIL, "[EMAIL]"),
        (_CNPJ, "[CNPJ]"),
        (_PIS, "[PIS]"),
        (_CPF, "[CPF]"),
        (_PHONE, "[TELEFONE]"),
    ):
        text = pattern.sub(marker, text)
    return text
