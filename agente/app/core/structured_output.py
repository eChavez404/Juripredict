"""Falhas controladas ao validar respostas estruturadas do provedor de IA."""

from langchain_core.exceptions import OutputParserException
from pydantic import ValidationError

STRUCTURED_OUTPUT_RETRY_ERRORS = (
    OutputParserException,
    ValidationError,
    ValueError,
)


class StructuredOutputError(RuntimeError):
    """A resposta do modelo não pôde ser validada após uma nova tentativa."""
