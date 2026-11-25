"""Isola os testes do .env: nenhum teste chega ao Google, ao Pinecone ou ao Langfuse reais.

O load_dotenv não sobrescreve variável já definida, mesmo vazia.
"""

import os

os.environ.update(
    {
        "LLM_MODEL": "google_genai:modelo-de-teste",
        "AGENTE_SEGREDO": "segredo-de-teste",
        "GOOGLE_API_KEY": "chave-de-teste",
        "PINECONE_API_KEY": "",
        "PINECONE_INDEX": "",
        "PINECONE_NAMESPACE": "",
        "LANGFUSE_PUBLIC_KEY": "",
        "LANGFUSE_SECRET_KEY": "",
    }
)
