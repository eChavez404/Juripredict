"""Traduz falhas da análise sem expor conteúdo ou cadeia de exceções."""

import logging
from uuid import uuid4

from fastapi import HTTPException
from langchain_core.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
)

from app.core.input_errors import NoCriteriaAvailable
from app.core.llm import LLMNotConfiguredError, LLMTimeoutError
from app.core.structured_output import StructuredOutputError
from app.core.vector_store import VectorStoreError

logger = logging.getLogger(__name__)


def analysis_error(exc: Exception, operation: str) -> HTTPException:
    if isinstance(exc, NoCriteriaAvailable):
        code, category = 422, "no_criteria"
        detail = "Ainda não há critérios cadastrados para esse tema."
    elif isinstance(exc, LLMNotConfiguredError):
        code, category = 503, "provider_not_configured"
        detail = "A chave do provedor de IA não está configurada no serviço."
    elif isinstance(exc, (ModelAuthenticationError, ModelPermissionDeniedError)):
        code, category = 503, "provider_credentials"
        detail = "O provedor de IA recusou a chave configurada no serviço."
    elif isinstance(exc, LLMTimeoutError):
        code, category = 503, "provider_timeout"
        detail = "O provedor de IA excedeu o tempo disponível. Tente novamente."
    elif isinstance(exc, ModelRateLimitError):
        code, category = 429, "provider_rate_limit"
        detail = "O limite de uso da IA foi atingido. Tente novamente mais tarde."
    elif isinstance(exc, ModelAPIError):
        code, category = 503, "provider_unavailable"
        detail = "O serviço de IA está sobrecarregado no momento. Tente de novo em instantes."
    elif isinstance(exc, VectorStoreError):
        code, category = 503, "vector_store"
        detail = "Não foi possível consultar a base de casos. Tente novamente em instantes."
    elif isinstance(exc, StructuredOutputError):
        code, category = 502, "structured_output"
        detail = "A resposta da IA não atendeu ao formato necessário. Tente novamente."
    else:
        code, category = 502, "analysis_failure"
        detail = "Não foi possível analisar o caso."
    error_id = uuid4().hex
    # Somente valores definidos pelo serviço e nomes de classe; nunca str(exc), prompt ou
    # resposta, que podem conter o relato do caso.
    logger.warning(
        "ai_analysis_failed operation=%s category=%s error=%s cause=%s error_id=%s",
        operation,
        category,
        type(exc).__name__,
        type(exc.__cause__).__name__,
        error_id,
    )
    return HTTPException(status_code=code, detail=detail, headers={"X-AI-Error-ID": error_id})
