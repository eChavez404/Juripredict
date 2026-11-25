from langchain.chat_models import init_chat_model

from app.core.config import (
    GOOGLE_API_KEY,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
    LLM_MODEL,
    LLM_PROVIDER_TIMEOUT_SECONDS,
)


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


def invoke_with_timeout_translation(structured_model, messages):
    """Traduz timeout sem registrar prompt, resposta ou mensagem da exceção."""

    try:
        return structured_model.invoke(messages)
    except Exception as exc:
        if _is_timeout_error(exc):
            raise LLMTimeoutError("O provedor de IA excedeu o tempo da tentativa.") from exc
        raise


def require_google_key() -> None:
    if not GOOGLE_API_KEY:
        raise LLMNotConfiguredError("GOOGLE_API_KEY não está definida.")


def model():
    """Modelo de chat definido em LLM_MODEL."""
    require_google_key()
    return init_chat_model(
        LLM_MODEL,
        # O raciocínio interno também conta em max_tokens; 16000 dá folga sem streaming.
        max_tokens=16000,
        # 1 = só a chamada original (a documentação do langchain-google-genai avisa que 0
        # pode virar o padrão do SDK, com 5 repetições). Retries multiplicariam o timeout;
        # a única repetição permitida é a correção manual de saída estruturada inválida.
        max_retries=1,
        timeout=LLM_PROVIDER_TIMEOUT_SECONDS,
    )


def langfuse_callbacks() -> list:
    """Handler do Langfuse para o config do grafo: um trace por requisição."""
    if not (LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY):
        return []
    from langfuse.langchain import CallbackHandler

    return [CallbackHandler()]
