import os
from pathlib import Path

from dotenv import load_dotenv

# Caminho explícito: sem ele, a busca sobe até o .env da raiz, com as chaves do Django (AST06).
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Painéis de hospedagem guardam as aspas e espaços colados junto com a chave, e aí o provedor a
# recusa. Corrige no próprio ambiente porque o SDK do Langfuse também lê dele.
for _name in (
    "GOOGLE_API_KEY",
    "LLM_MODEL",
    "LLM_FALLBACK_MODEL",
    "EMBEDDING_MODEL",
    "AGENTE_SEGREDO",
):
    if _name in os.environ:
        os.environ[_name] = os.environ[_name].strip().strip("\"'").strip()
for _name in list(os.environ):
    if _name.startswith(("PINECONE_", "LANGFUSE_")):
        os.environ[_name] = os.environ[_name].strip().strip("\"'").strip()

# Configurações do aplicativo
APP_NAME = "Agente JuriPredict"
DESCRIPTION = "Mede um caso trabalhista, aponta o que melhorar e traz os casos mais próximos."
VERSION = (os.getenv("APP_VERSION", "0.1.0") or "").strip()

# O mesmo AGENTE_SEGREDO do backend Django. Sem ele, a API recusa todas as chamadas.
AGENTE_SEGREDO = (os.getenv("AGENTE_SEGREDO") or "").strip()

# Modelo no formato provedor:modelo (init_chat_model). O GOOGLE_API_KEY também é lido
# pelo próprio SDK a partir do .env.
LLM_MODEL = (os.getenv("LLM_MODEL") or "").strip()
# Usado só quando o principal segue indisponível depois das repetições. Vazio desliga.
LLM_FALLBACK_MODEL = os.getenv("LLM_FALLBACK_MODEL", "google_genai:gemini-3.5-flash-lite").strip()
GOOGLE_API_KEY = (os.getenv("GOOGLE_API_KEY") or "").strip()

# Sem as duas chaves, nada é enviado ao Langfuse.
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")

# Sem chave e índice, o agente roda sem casos próximos e registra isso na resposta.
PINECONE_API_KEY = (os.getenv("PINECONE_API_KEY") or "").strip()
PINECONE_INDEX = (os.getenv("PINECONE_INDEX") or "").strip()
PINECONE_NAMESPACE = (os.getenv("PINECONE_NAMESPACE") or "").strip()

EMBEDDING_MODEL = (os.getenv("EMBEDDING_MODEL") or "gemini-embedding-2").strip()

# 8000 é a porta do backend Django do JuriPredict.
PORT = int(os.getenv("PORT", "8001"))
HOST = os.getenv("HOST", "127.0.0.1")


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} deve ser um inteiro.") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} deve estar entre {minimum} e {maximum}.")
    return value


# Sem retry automático no SDK: no pior caso são duas tentativas (a original e
# uma correção de saída estruturada), cada uma limitada a este tempo.
LLM_PROVIDER_TIMEOUT_SECONDS = _bounded_int(
    "LLM_PROVIDER_TIMEOUT_SECONDS", 120, minimum=1, maximum=300
)
# Precisa ser igual à dimensão do índice no Pinecone.
EMBEDDING_DIMENSIONS = _bounded_int("EMBEDDING_DIMENSIONS", 768, minimum=128, maximum=3072)

if not LLM_MODEL:
    raise ValueError("A variável de ambiente LLM_MODEL não está definida (provedor:modelo).")
if not VERSION:
    raise ValueError("A variável de ambiente APP_VERSION não pode ser vazia.")
