"""Traduz falhas da análise sem expor conteúdo ou cadeia de exceções."""

import logging
from uuid import uuid4

from fastapi import HTTPException
from langchain_core.exceptions import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelConnectionError,
    ModelInvalidRequestError,
    ModelNotFoundError,
    ModelPermissionDeniedError,
    ModelRateLimitError,
)

from app.core.guardrails import GuardrailBlocked, UnsafeInput
from app.core.input_errors import NoCriteriaAvailable
from app.core.llm import LLMNotConfiguredError, LLMTimeoutError, provider_status
from app.core.structured_output import StructuredOutputError

logger = logging.getLogger(__name__)


def _invalid_key(exc: Exception) -> bool:
    """O Google recusa chave inválida com 400, o mesmo código de pedido malformado."""
    return isinstance(exc, ModelInvalidRequestError) and "API key not valid" in str(exc)


def analysis_error(exc: Exception, operation: str) -> HTTPException:
    if isinstance(exc, NoCriteriaAvailable):
        code, category = 422, "no_criteria"
        detail = "Ainda não há critérios cadastrados para esse tema."
    elif isinstance(exc, LLMNotConfiguredError):
        code, category = 503, "provider_not_configured"
        detail = "A chave do provedor de IA não está configurada no serviço."
    elif isinstance(exc, UnsafeInput):
        code, category = 422, "guardrail_input"
        detail = (
            "O texto contém um trecho que parece um comando para a IA. "
            "Reescreva esse trecho e envie de novo."
        )
    elif isinstance(exc, GuardrailBlocked):
        code, category = 502, "guardrail_output"
        detail = "A resposta da IA foi recusada pelas regras de segurança. Tente novamente."
    elif _invalid_key(exc) or isinstance(
        exc, (ModelAuthenticationError, ModelPermissionDeniedError)
    ):
        code, category = 503, "provider_credentials"
        detail = "O provedor de IA recusou a chave configurada no serviço."
    elif isinstance(exc, ModelNotFoundError):
        code, category = 503, "provider_model"
        detail = "O modelo de IA configurado não existe ou não está liberado para a chave."
    elif isinstance(exc, ModelInvalidRequestError):
        code, category = 502, "provider_request"
        detail = "O provedor de IA recusou o formato do pedido."
    elif isinstance(exc, LLMTimeoutError):
        code, category = 503, "provider_timeout"
        detail = "O provedor de IA excedeu o tempo disponível. Tente novamente."
    elif isinstance(exc, ModelRateLimitError):
        code, category = 429, "provider_rate_limit"
        detail = "O limite de uso da IA foi atingido. Tente novamente mais tarde."
    elif isinstance(exc, (ModelAPIError, ModelConnectionError)):
        code, category = 503, "provider_unavailable"
        detail = "O serviço de IA está sobrecarregado no momento. Tente de novo em instantes."
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
        "ai_analysis_failed operation=%s category=%s rules=%s error=%s cause=%s status=%s "
        "error_id=%s",
        operation,
        category,
        ",".join(getattr(exc, "rules", ())),
        type(exc).__name__,
        type(exc.__cause__).__name__,
        provider_status(exc),
        error_id,
    )
    # O código aparece na tela: é por ele que se acha a linha do log.
    status = provider_status(exc).split(" ")[0]
    label = category if status == "-" else f"{category} {status}"
    detail = f"{detail} (código: {label} · {error_id[:8]})"
    return HTTPException(status_code=code, detail=detail, headers={"X-AI-Error-ID": error_id})
