"""Remoção de dados pessoais com formato conhecido antes de qualquer envio a terceiros."""

import re

# O número CNJ do processo não casa com nenhum dos dois e é preservado.
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def mask_documents(text: str) -> str:
    """Troca CPF e CNPJ por marcadores. Nomes não são cobertos."""
    return _CPF.sub("[CPF]", _CNPJ.sub("[CNPJ]", text))
