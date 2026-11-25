"""
Exporta a base da jurimetria do tribunal: o CSV que o backend importa
(`python manage.py importar_decisoes_trt`).

    python processar.py --entrada C:/dados/falcao-trt16/normalized --somente sentencas \\
        --temas insalubridade,periculosidade --banco ../data/trt16.db \\
        --manifest C:/dados/falcao-trt16/manifests/falcao.sqlite
    python exportar_jurimetria.py --banco ../data/trt16.db --saida ../data/jurimetria_trt16.csv \\
        --rag ../data/rag_trt16.jsonl

Com --rag, gera tambem os trechos que o agente indexa no Pinecone (`python -m app.indexar`):
so as decisoes que entram na taxa, porque o agente mostra o que foi deferido e o que nao foi.

Uma linha por (processo, pedido), inclusive as que nao entram na taxa: a populacao e o
motivo vem do mesmo `montar()` do dataset (I1), entao nada some em silencio. O trecho do
dispositivo sai sem nome de parte (I6). O arquivo fica fora do Git: tem numero de processo.
"""

import argparse
import csv
import json
import os
import re
import sqlite3
import sys
from collections import Counter

# A base do tribunal usa as correcoes de coerencia (acao coletiva, reflexo, extincao).
os.environ.setdefault("JURIPREDICT_VERSAO", "2.0")

from gold_set import mecanismo  # noqa: E402
from montar_dataset import carregar, montar  # noqa: E402
from processar import VERSAO_REGRA  # noqa: E402
from rotular_por_regra import VERSAO_DATASET  # noqa: E402

TEMAS = ("insalubridade", "periculosidade")
# Trechos do RAG: pedacos do capitulo do tema na fundamentacao, mais o dispositivo.
TAMANHO, SOBRA, MAX_TRECHOS = 1500, 200, 4
COLUNAS = [
    "caso_id", "numero_cnj", "tema", "vara", "data_sentenca", "resultado",
    "grau", "populacao", "motivo_fora", "mecanismo", "trecho", "versao",
]

_PALAVRA = re.compile(r"\b[^\W\d_][^\W\d_'-]{2,}\b")
_DOCUMENTO = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b|\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_TRATAMENTO = re.compile(r"\b(?:Sr|Sra|Dr|Dra|Srta)\.?\s+(?:\[parte\]\s*)+")
# Um nome completo e uma sequencia de palavras com maiuscula, ligadas por "da", "de", "e"...
# Basta uma delas ter sido mascarada para a sequencia inteira ser o nome: sem isso sobravam
# pedacos como "[parte] DIAS [parte]" ou "EMPRESA BRASILEIRA DE [parte]".
_MAIUSCULA = r"(?:[A-ZÀ-Ý][\wÀ-ÿ.&'/-]*|\[parte\])"
_SEQUENCIA = re.compile(rf"{_MAIUSCULA}(?:\s+(?:(?:da|de|do|dos|das|e|&)\s+)?{_MAIUSCULA})*")
# Termos do proprio texto juridico que aparecem com inicial maiuscula com frequencia.
_SIGLAS_E_TERMOS = {"clt", "nr", "fgts", "tst", "trt", "stf", "inss", "ctps", "epi", "ppp",
                    "ltcat", "pcmso", "ppra", "pgr", "cpc", "oj", "sdi", "cpf", "cnpj", "pis",
                    "sr", "sra", "srta", "dr", "dra"}


def vocabulario(textos):
    """Quantas vezes cada palavra aparece escrita toda em minuscula no corpus."""
    minusculas = Counter()
    for texto in textos:
        minusculas.update(p for p in _PALAVRA.findall(texto or "") if p.islower())
    return minusculas


def pseudonimizar(trecho, minusculas, minimo=3):
    """Troca por [parte] a palavra com inicial maiuscula que quase nunca aparece minuscula.

    Nome de pessoa e de empresa nao vira palavra comum ("Silva", "Suzano"); palavra comum
    em maiuscula ("JULGO", "Adicional") aparece minuscula no resto do corpus. E heuristica:
    uma empresa com nome de palavra comum ("Vale") passa.
    """
    def trocar(achado):
        palavra = achado.group(0)
        baixa = palavra.lower()
        verbo = achado.string[achado.end():achado.end() + 3] in ("-se", "-lh", "-me")  # Intime-se
        if palavra.islower() or verbo or baixa in _SIGLAS_E_TERMOS or minusculas[baixa] >= minimo:
            return palavra
        return "[parte]"

    texto = _DOCUMENTO.sub("[documento]", trecho or "")
    texto = _PALAVRA.sub(trocar, texto)
    texto = _SEQUENCIA.sub(lambda m: "[parte]" if "[parte]" in m.group(0) else m.group(0), texto)
    return _TRATAMENTO.sub("[parte] ", texto).strip()


def fatiar(texto, tamanho=TAMANHO, sobra=SOBRA):
    """Pedacos de ate `tamanho` caracteres, cortados em espaco, com `sobra` de contexto."""
    texto = " ".join(texto.split())
    pedacos, inicio = [], 0
    while inicio < len(texto):
        fim = len(texto) if len(texto) - inicio <= tamanho else texto.rfind(" ", inicio, inicio + tamanho)
        fim = fim if fim > inicio else inicio + tamanho
        pedacos.append(texto[inicio:fim])
        if fim >= len(texto):
            break
        inicio = max(fim - sobra, inicio + 1)
        inicio = texto.find(" ", inicio) + 1 or inicio
    return pedacos


def trechos_rag(linhas, capitulos, minusculas):
    """Um registro por trecho, no formato que `app.indexar` envia ao Pinecone."""
    for linha in linhas:
        if linha["populacao"] != "modelo":
            continue
        pedacos = fatiar(pseudonimizar(capitulos.get(linha["caso_id"], ""), minusculas))
        pedacos = pedacos[: MAX_TRECHOS - 1] if linha["trecho"] else pedacos[:MAX_TRECHOS]
        if linha["trecho"]:
            pedacos.append(f"Dispositivo: {linha['trecho']}")
        for i, texto in enumerate(pedacos):
            yield {
                "id": f"{linha['caso_id']}#{i}",
                "id_sentenca": linha["caso_id"],
                "numero_cnj": linha["numero_cnj"],
                "tipo_documento": "Sentença",
                "orgao_julgador": linha["vara"],
                "data_julgamento": linha["data_sentenca"],
                "resultado": linha["resultado"],
                "tema": linha["tema"],
                "texto": texto[:8000],
            }


def exportar(banco, saida, rag=None):
    docs, casos, valores = carregar(banco)
    con = sqlite3.connect(banco)
    evidencias = dict(con.execute(
        "SELECT caso_id, evidencia FROM valores WHERE campo = 'resultado_pedido'"))
    metodos = dict(con.execute(
        "SELECT caso_id, metodo FROM valores WHERE campo = 'resultado_pedido'"))
    capitulos = dict(con.execute("SELECT caso_id, texto FROM capitulos"))
    con.close()
    minusculas = vocabulario([*capitulos.values(), *evidencias.values()])

    linhas = []
    for tema in TEMAS:
        df, _ = montar(docs, casos, valores, pedido=tema)
        for r in df.to_dict("records"):
            evidencia = evidencias.get(r["caso_id"], "")
            grau = r.get("grau_deferido")
            linhas.append({
                "caso_id": r["caso_id"],
                "numero_cnj": r["numero_cnj"],
                "tema": tema,
                "vara": r.get("vara") or "",
                "data_sentenca": str(r.get("data_sentenca") or "")[:10],
                "resultado": r["resultado_pedido"],
                "grau": int(grau) if grau == grau and grau else "",
                "populacao": r["populacao"],
                "motivo_fora": r.get("motivo_fora") or "",
                "mecanismo": mecanismo(metodos.get(r["caso_id"]), evidencia),
                # "inferido: ..." e a explicacao da regra, nao texto da sentenca
                "trecho": "" if evidencia.startswith("inferido") else pseudonimizar(evidencia, minusculas),
                "versao": f"{VERSAO_DATASET}/{VERSAO_REGRA}",
            })

    with open(saida, "w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUNAS)
        escritor.writeheader()
        escritor.writerows(linhas)
    contagem = Counter((linha["tema"], linha["populacao"]) for linha in linhas)
    print(f"{len(linhas)} linhas em {saida}")
    for (tema, populacao), n in sorted(contagem.items()):
        print(f"  {tema:<15} {populacao:<18} {n:>6}")
    if rag:
        with open(rag, "w", encoding="utf-8") as f:
            total = 0
            for trecho in trechos_rag(linhas, capitulos, minusculas):
                f.write(json.dumps(trecho, ensure_ascii=False) + "\n")
                total += 1
        print(f"{total} trechos do RAG em {rag}")
    return linhas


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="../data/trt16.db")
    ap.add_argument("--saida", default="../data/jurimetria_trt16.csv")
    ap.add_argument("--rag", help="JSONL com os trechos para o Pinecone")
    a = ap.parse_args()
    if not os.path.exists(a.banco):
        sys.exit(f"banco nao encontrado: {a.banco}. Rode processar.py antes.")
    exportar(a.banco, a.saida, a.rag)
