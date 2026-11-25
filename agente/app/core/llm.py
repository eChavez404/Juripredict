import logging
import random
import time
from collections.abc import Callable

from langchain.chat_models import init_chat_model
from langchain_core.exceptions import ModelAPIError, ModelConnectionError, ModelRateLimitError
from pydantic import BaseModel

from app.core.config import (
    GOOGLE_API_KEY,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LLM_FALLBACK_MODEL,
    LLM_MODEL,
    LLM_PROVIDER_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

# Falhas passageiras do provedor. A orientação do Google para 5xx é repetir com espera crescente.
TRANSIENT_ERRORS = (ModelAPIError, ModelConnectionError, ModelRateLimitError)
RETRY_DELAYS_SECONDS = (2, 5)


class LLMTimeoutError(TimeoutError):
    """O provedor não respondeu dentro do tempo de uma tentativa."""


class LLMNotConfiguredError(RuntimeError):
    """Falta a chave do provedor no ambiente."""


_TIMEOUT_CLASS_NAMES = {
    "ConnectTimeout",
    "DeadlineExceeded",
    "ReadTimeout",
    "TimeoutError",
    "TimeoutException",
    "WriteTimeout",
}


def _is_timeout_error(error: BaseException) -> bool:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, TimeoutError):
            return True
        if current.__class__.__name__ in _TIMEOUT_CLASS_NAMES:
            return True
        current = current.__cause__ or current.__context__
    return False


def provider_status(error: BaseException) -> str:
    """Código do provedor, como "503 UNAVAILABLE". Só número e nome fixo: seguro para o log."""
    cause = error.__cause__
    code, status = getattr(cause, "code", None), getattr(cause, "status", None)
    parts = [str(code) if isinstance(code, int) else ""]
    parts.append(status if isinstance(status, str) and status.replace("_", "").isalpha() else "")
    return " ".join(filter(None, parts)) or "-"


def invoke_with_timeout_translation(structured_model, messages):
    """Traduz timeout sem registrar prompt, resposta ou mensagem da exceção."""

    try:
        return structured_model.invoke(messages)
    except Exception as exc:
        if _is_timeout_error(exc):
            raise LLMTimeoutError("O provedor de IA excedeu o tempo da tentativa.") from exc
        raise


def invoke_with_retry(build: Callable[[str], object], messages) -> tuple[object, bool]:
    """Chama o modelo, repetindo só falha passageira. Devolve a resposta e se usou o reserva.

    Timeout não é repetido: cada tentativa já pode levar minutos.
    """
    plan = [(LLM_MODEL, delay) for delay in RETRY_DELAYS_SECONDS]
    plan.append((LLM_FALLBACK_MODEL or LLM_MODEL, None))
    for name, delay in plan:
        try:
            answer = invoke_with_timeout_translation(build(name), messages)
            return answer, name != LLM_MODEL
        except TRANSIENT_ERRORS as exc:
            logger.warning(
                "llm_transient_failure model=%s error=%s status=%s",
                name,
                type(exc).__name__,
                provider_status(exc),
            )
            if delay is None:
                raise
            # A variação evita que pedidos simultâneos voltem todos no mesmo instante.
            time.sleep(delay + random.uniform(0, delay / 2))
    raise AssertionError("Plano de tentativas vazio.")


def provider_schema(schema: type[BaseModel]) -> dict:
    """Schema sem os limites de tamanho: o provedor ignora os de texto, e os de lista multiplicam
    a complexidade (o Google recusa schema complexo demais). O Pydantic confere todos depois."""

    def clean(node):
        if isinstance(node, list):
            return [clean(item) for item in node]
        if not isinstance(node, dict):
            return node
        limits = {"minLength", "maxLength", "minItems", "maxItems"}
        return {key: clean(value) for key, value in node.items() if key not in limits}

    return clean(schema.model_json_schema())


def require_google_key() -> None:
    if not GOOGLE_API_KEY:
        raise LLMNotConfiguredError("GOOGLE_API_KEY não está definida.")


def model(name: str = LLM_MODEL):
    """Modelo de chat, no formato provedor:modelo."""
    require_google_key()
    return init_chat_model(
        name,
        api_key=GOOGLE_API_KEY,
        # O raciocínio interno também conta em max_tokens; 16000 dá folga sem streaming.
        max_tokens=16000,
        # 1 = só a chamada original (a documentação do langchain-google-genai avisa que 0
        # pode virar o padrão do SDK, com 5 repetições). Quem repete é o invoke_with_retry.
        max_retries=1,
        timeout=LLM_PROVIDER_TIMEOUT_SECONDS,
    )


def langfuse_callbacks() -> list:
    """Handler do Langfuse para o config do grafo: um trace por requisição."""
    if not (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        return []
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler()]
