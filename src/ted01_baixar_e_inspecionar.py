"""TED 01: baixa a base do Kaggle, confere a integridade e descreve a estrutura.

Uso: python src/ted01_baixar_e_inspecionar.py
A pasta dos dados pode ser trocada com a variável de ambiente DADOS_DIR.
"""

import hashlib
import json
import os
import statistics as st
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DADOS = Path(os.environ.get("DADOS_DIR", RAIZ / "data"))
RAW = DADOS / "raw"
RESULTADOS = RAIZ / "resultados"

URL = "https://www.kaggle.com/api/v1/datasets/download/felipepolo/brazilian-legal-proceedings/{}"
# Versão 2 da base, publicada em 14/05/2021.
SHA256 = {
    "labeled.json": "653013a741af31ad389f44458bc0bf5fd4c78a380646556d0772dee47846c63a",
    "unlabeled.json": "0451bc19da272cd849a25e510d44ad1735f42a51436514eff114bba7fece3042",
}


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def baixar(nome):
    destino = RAW / nome
    if not destino.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        compactado = destino.with_suffix(".zip")
        print(f"baixando {nome}...")
        urllib.request.urlretrieve(URL.format(nome), compactado)
        with zipfile.ZipFile(compactado) as z:
            z.extract(nome, RAW)
        compactado.unlink()
    obtido = sha256(destino)
    if obtido != SHA256[nome]:
        raise SystemExit(f"{nome}: SHA-256 {obtido} difere da versão documentada")
    return destino


def main():
    rotulado = json.loads(baixar("labeled.json").read_text(encoding="utf-8"))
    sem_rotulo = json.loads(baixar("unlabeled.json").read_text(encoding="utf-8"))

    n_mov = [len(p["texts"]) for p in rotulado.values()]
    chars = [len(t) for p in rotulado.values() for t in p["texts"].values()]
    resumo = {
        "versao_kaggle": 2,
        "sha256": SHA256,
        "bytes": {n: (RAW / n).stat().st_size for n in SHA256},
        "rotulado": {
            "processos": len(rotulado),
            "movimentacoes": sum(n_mov),
            "atributos_por_processo": sorted({k for p in rotulado.values() for k in p}),
            "rotulos": Counter(p["label"] for p in rotulado.values()),
            "movimentacoes_por_processo": {
                "min": min(n_mov), "mediana": st.median(n_mov),
                "media": round(st.mean(n_mov), 2), "max": max(n_mov),
            },
            "caracteres_por_movimentacao": {
                "min": min(chars), "mediana": st.median(chars),
                "media": round(st.mean(chars), 2), "max": max(chars),
            },
        },
        "sem_rotulo": {
            "movimentacoes": len(sem_rotulo),
            "textos_distintos": len(set(sem_rotulo.values())),
            "vazios": sum(1 for t in sem_rotulo.values() if not t),
        },
    }
    RESULTADOS.mkdir(exist_ok=True)
    saida = RESULTADOS / "ted01_inspecao.json"
    saida.write_text(json.dumps(resumo, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(resumo, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
