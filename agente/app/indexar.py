"""Indexa no Pinecone os trechos de sentenças gerados pelo pipeline.

    uv run python -m app.indexar ../dataset/data/rag_trt16.jsonl

O arquivo vem de `dataset/pipeline/exportar_jurimetria.py --rag`, já sem nome de parte. Cria o
índice se ele não existir (768 dimensões, cosseno) e retoma de onde parou: os ids já enviados
ficam em `<arquivo>.indexados`. Usa GOOGLE_API_KEY, PINECONE_API_KEY e PINECONE_INDEX do .env.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from google.genai.types import EmbedContentConfig

from app.core import vector_store
from app.core.config import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    PINECONE_API_KEY,
    PINECONE_INDEX,
    PINECONE_NAMESPACE,
)
from app.core.llm import require_google_key

LOTE = 50
# Os limites do plano gratuito do Gemini são por minuto: uma pausa curta entre os lotes evita o 429.
PAUSA_SEGUNDOS = 1.0
METADADOS = (
    "id_sentenca",
    "numero_cnj",
    "tipo_documento",
    "orgao_julgador",
    "data_julgamento",
    "resultado",
)


def documento(trecho: dict) -> str:
    """Formato de documento do gemini-embedding-2 (a consulta usa `task: search result`)."""
    return f"title: {trecho['tema']} · {trecho['orgao_julgador']} | text: {trecho['texto']}"


def metadados(trecho: dict) -> dict:
    # O Pinecone não aceita nulo nos metadados; campo vazio fica de fora.
    dados = {campo: trecho[campo] for campo in METADADOS if trecho.get(campo)}
    return {**dados, "texto": trecho["texto"], "temas": [trecho["tema"]]}


def garantir_indice(pinecone) -> None:
    if pinecone.has_index(PINECONE_INDEX):
        return
    from pinecone import ServerlessSpec

    print(f"criando o índice {PINECONE_INDEX} ({EMBEDDING_DIMENSIONS} dimensões, cosseno)")
    pinecone.create_index(
        name=PINECONE_INDEX,
        dimension=EMBEDDING_DIMENSIONS,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )


def indexar(arquivo: Path, *, pinecone=None, genai=None, pausa=PAUSA_SEGUNDOS) -> int:
    require_google_key()
    if not (PINECONE_API_KEY and PINECONE_INDEX):
        raise SystemExit("Preencha PINECONE_API_KEY e PINECONE_INDEX no .env do agente.")
    if pinecone is None:
        from pinecone import Pinecone

        pinecone = Pinecone(api_key=PINECONE_API_KEY)
    genai = genai or vector_store._genai_client()
    garantir_indice(pinecone)
    indice = pinecone.Index(PINECONE_INDEX)

    feitos_arquivo = arquivo.with_name(arquivo.name + ".indexados")
    feitos = (
        set(feitos_arquivo.read_text(encoding="utf-8").split())
        if feitos_arquivo.exists()
        else set()
    )
    with arquivo.open(encoding="utf-8") as linhas:
        pendentes = [t for t in map(json.loads, linhas) if t["id"] not in feitos]
    print(f"{len(feitos)} trechos já indexados; {len(pendentes)} a enviar")

    enviados = 0
    for inicio in range(0, len(pendentes), LOTE):
        lote = pendentes[inicio : inicio + LOTE]
        resposta = genai.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[documento(t) for t in lote],
            config=EmbedContentConfig(output_dimensionality=EMBEDDING_DIMENSIONS),
        )
        vetores = [
            {"id": t["id"], "values": list(e.values), "metadata": metadados(t)}
            for t, e in zip(lote, resposta.embeddings, strict=True)
        ]
        indice.upsert(vectors=vetores, namespace=PINECONE_NAMESPACE)
        with feitos_arquivo.open("a", encoding="utf-8") as saida:
            saida.writelines(f"{t['id']}\n" for t in lote)
        enviados += len(lote)
        print(f"  {len(feitos) + enviados} de {len(feitos) + len(pendentes)}")
        if pausa:
            time.sleep(pausa)
    return enviados


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("arquivo", type=Path, help="JSONL do exportar_jurimetria.py --rag")
    a = p.parse_args()
    if not a.arquivo.exists():
        sys.exit(f"arquivo não encontrado: {a.arquivo}")
    print(f"{indexar(a.arquivo)} trechos enviados ao índice {PINECONE_INDEX}.")
