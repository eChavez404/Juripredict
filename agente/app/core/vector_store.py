"""Busca dos casos mais próximos na base vetorial (Pinecone).

A base ainda não existe: este módulo só lê, e define o contrato que a indexação
precisa gravar nos metadados de cada vetor (`RetrievedCase` e `temas`).
"""

from functools import lru_cache

from google import genai
from google.genai.types import EmbedContentConfig, HttpOptions
from pinecone import Pinecone
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    GOOGLE_API_KEY,
    PINECONE_API_KEY,
    PINECONE_INDEX,
    PINECONE_NAMESPACE,
)
from app.core.llm import require_google_key

EMBEDDING_TIMEOUT_MS = 30_000
# O SDK repete a chamada em caso de timeout: o pior caso é cerca de 5x este valor.
PINECONE_TIMEOUT_SECONDS = 5
# Um documento vira vários trechos: busca mais trechos do que casos e fica com o melhor de cada.
CHUNKS_PER_CASE = 4


class VectorStoreError(RuntimeError):
    """A busca falhou ou devolveu registro fora do contrato."""


class RetrievedCase(BaseModel):
    """Metadados esperados em cada vetor. Os nomes seguem o manifesto do coletor do Falcão.

    TODO(base): contrato provisório, a fechar quando a base for definida. `temas` (lista com
    os valores de `Theme`) também é obrigatório no índice, porque filtra a busca. `texto` deve
    ser indexado sem nomes das partes: ele vai para o modelo e para o Langfuse.
    """

    model_config = ConfigDict(extra="ignore")

    id_sentenca: str = Field(min_length=1, max_length=80)
    texto: str = Field(min_length=1, max_length=8000)
    similaridade: float
    numero_cnj: str | None = Field(default=None, max_length=40)
    tipo_documento: str | None = Field(default=None, max_length=120)
    orgao_julgador: str | None = Field(default=None, max_length=200)
    data_julgamento: str | None = Field(default=None, max_length=20)
    resultado: str | None = Field(default=None, max_length=60)


def is_configured() -> bool:
    return bool(PINECONE_API_KEY and PINECONE_INDEX)


@lru_cache(maxsize=1)
def _index():
    return Pinecone(api_key=PINECONE_API_KEY, timeout=PINECONE_TIMEOUT_SECONDS).index(
        PINECONE_INDEX
    )


# SDK do Google direto: o wrapper de embeddings do LangChain não limita o tempo da chamada
# e sempre envia task_type, que o gemini-embedding-2 não aceita (a tarefa vai no texto).
@lru_cache(maxsize=1)
def _genai_client():
    return genai.Client(
        api_key=GOOGLE_API_KEY, http_options=HttpOptions(timeout=EMBEDDING_TIMEOUT_MS)
    )


def embed_query(text: str) -> list[float]:
    """Vetor da consulta. Os documentos devem ser indexados como `title: ... | text: ...`."""
    response = _genai_client().models.embed_content(
        model=EMBEDDING_MODEL,
        contents=[f"task: search result | query: {text}"],
        config=EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
    )
    return list(response.embeddings[0].values)


def search_cases(query: str, tema: str, limit: int) -> list[RetrievedCase]:
    """Os `limit` documentos mais próximos do tema, do mais ao menos parecido."""
    require_google_key()
    try:
        response = _index().query(
            vector=embed_query(query),
            top_k=limit * CHUNKS_PER_CASE,
            namespace=PINECONE_NAMESPACE,
            filter={"temas": {"$in": [tema]}},
            include_metadata=True,
        )
        # Registro fora do contrato é defeito da indexação: falha alto em vez de sumir.
        chunks = [
            RetrievedCase.model_validate({**(match.metadata or {}), "similaridade": match.score})
            for match in response.matches
        ]
    except Exception as exc:
        raise VectorStoreError("A busca na base de casos falhou.") from exc
    best: dict[str, RetrievedCase] = {}
    for chunk in chunks:  # já vêm ordenados por similaridade
        best.setdefault(chunk.id_sentenca, chunk)
    return list(best.values())[:limit]
