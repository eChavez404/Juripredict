"""
Divide o dataset em treino / calibracao / teste por CORTE TEMPORAL.

    python dividir_dataset.py                 # confere a particao ja gravada
    python dividir_dataset.py --treino 0.7 --calibracao 0.15 --gravar
    python dividir_dataset.py --demo          # roda com dados falsos, sem arquivo

Quem grava a coluna `particao` no arquivo unico e o montar_dataset.py, usando as
funcoes deste modulo. Aqui o uso normal e CONFERIR o corte e a deriva entre as
particoes; `--gravar` recorta com outras proporcoes e regrava o mesmo arquivo.

Tres decisoes que este script implementa por codigo, para nao depender de
disciplina na hora de avaliar:

  1. A divisao NUNCA e aleatoria (invariante I5). Sentenca e serie temporal:
     entendimento muda, perito muda, vara muda. Embaralhar as datas deixa o
     modelo ver o futuro e infla toda metrica sem que isso apareca em lugar
     nenhum.

  2. A calibracao tem particao PROPRIA. Calibrar no teste e depois reportar o
     escore de Brier do mesmo teste e medir o proprio ajuste.

  3. O corte cai em fronteira de DATA, nao de linha. Duas sentencas do mesmo
     dia, da mesma vara, saidas do mesmo laudo, nao podem ficar uma de cada
     lado. Por isso as proporcoes finais desviam de 60/20/20 - e o relatorio
     mostra o desvio em vez de esconde-lo.

So a populacao do modelo e particionada: linha de escape com particao
convidaria a inclui-la na avaliacao.
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

PARTICOES = ("treino", "calibracao", "teste")

# abaixo disto a particao nao sustenta estimativa de desempenho, so inspecao
PISO_TESTE = 100


def cortes_temporais(datas, p_treino=0.60, p_calibracao=0.20):
    """
    Devolve (corte1, corte2): as duas datas que separam as particoes.

    Escolhe o quantil e depois EMPURRA o corte para a proxima data distinta,
    de modo que nenhuma data apareca em duas particoes.
    """
    d = pd.to_datetime(pd.Series(datas)).dropna().sort_values()
    if d.empty:
        sys.exit("nenhuma data valida em data_sentenca.")

    distintas = d.drop_duplicates().to_numpy()
    if len(distintas) < 3:
        sys.exit(f"so {len(distintas)} data(s) distinta(s): corte temporal "
                 f"impossivel. Colete mais periodo antes de avaliar.")

    def fronteira(p):
        alvo = np.datetime64(d.quantile(p))
        posteriores = distintas[distintas > alvo]
        return posteriores[0] if len(posteriores) else distintas[-1]

    corte1 = fronteira(p_treino)
    corte2 = fronteira(p_treino + p_calibracao)
    if corte2 <= corte1:
        posteriores = distintas[distintas > corte1]
        corte2 = posteriores[0] if len(posteriores) else corte1
    return pd.Timestamp(corte1), pd.Timestamp(corte2)


def atribuir(df, corte1, corte2, coluna="data_sentenca"):
    """Marca cada linha com sua particao. Linha sem data fica de fora."""
    data = pd.to_datetime(df[coluna])
    particao = pd.Series("teste", index=df.index, dtype=object)
    particao[data < corte1] = "treino"
    particao[(data >= corte1) & (data < corte2)] = "calibracao"
    particao[data.isna()] = None
    return particao


def dividir(df, p_treino, p_calibracao):
    if "data_sentenca" not in df.columns:
        sys.exit("dataset sem coluna data_sentenca: nao da para cortar no tempo.")

    sem_data = pd.to_datetime(df["data_sentenca"]).isna().sum()
    corte1, corte2 = cortes_temporais(df["data_sentenca"], p_treino, p_calibracao)
    df = df.copy()
    df["particao"] = atribuir(df, corte1, corte2)
    return df, corte1, corte2, int(sem_data)


def relatorio(df, corte1, corte2, sem_data, p_treino, p_calibracao):
    print("=" * 74)
    print("DIVISAO TEMPORAL DO DATASET")
    print("=" * 74)
    print(f"  corte treino  -> calibracao : {corte1.date()}")
    print(f"  corte calibr. -> teste      : {corte2.date()}")
    if sem_data:
        print(f"  linhas sem data_sentenca    : {sem_data}  <- fora de toda particao")

    alvo = {"treino": p_treino, "calibracao": p_calibracao,
            "teste": 1 - p_treino - p_calibracao}
    total = int(df["particao"].notna().sum())

    cab = f"{'particao':<14}{'n':>7}{'%':>7}{'alvo':>7}{'periodo':>26}{'taxa-base':>11}"
    print("\n" + cab)
    for nome in PARTICOES:
        parte = df[df["particao"] == nome]
        n = len(parte)
        if not n:
            print(f"{nome:<14}{0:>7}{'':>7}{alvo[nome]:>7.0%}{'(vazia)':>26}")
            continue
        d0 = pd.to_datetime(parte["data_sentenca"]).min().date()
        d1 = pd.to_datetime(parte["data_sentenca"]).max().date()
        periodo = f"{d0} a {d1}"
        taxa = parte["y"].mean() if "y" in parte.columns else float("nan")
        print(f"{nome:<14}{n:>7}{n/max(total,1):>7.0%}{alvo[nome]:>7.0%}"
              f"{periodo:>26}{taxa:>11.1%}")

    print("\n" + "-" * 74)
    avisos = []

    n_teste = int((df["particao"] == "teste").sum())
    if n_teste < PISO_TESTE:
        avisos.append(
            f"teste com {n_teste} linhas (piso: {PISO_TESTE}). O intervalo de "
            f"confianca do\n  ganho sobre a taxa-base vai cruzar zero. Serve para "
            f"validar o pipeline;\n  nao sustenta afirmacao preditiva.")

    if "y" in df.columns:
        taxas = {nome: df[df["particao"] == nome]["y"].mean()
                 for nome in PARTICOES if (df["particao"] == nome).any()}
        if len(taxas) > 1:
            amplitude = max(taxas.values()) - min(taxas.values())
            if amplitude > 0.10:
                avisos.append(
                    f"taxa-base varia {amplitude:.0%} entre as particoes. Isso e "
                    f"deriva normativa,\n  nao ruido: o modelo treinado no inicio do "
                    f"periodo esta prevendo outro\n  regime. Reporte a taxa-base da "
                    f"particao de teste como linha de base.")

    if "vara" in df.columns:
        varas_treino = set(df[df["particao"] == "treino"]["vara"].dropna())
        novas = set(df[df["particao"] == "teste"]["vara"].dropna()) - varas_treino
        if novas:
            avisos.append(
                f"{len(novas)} unidade(s) aparecem so no teste: "
                f"{sorted(novas)[:3]}\n  Qualquer feature por vara vai estar ausente "
                f"para elas. Decida o tratamento\n  antes de treinar, nao depois de "
                f"ver a metrica.")

    if avisos:
        for aviso in avisos:
            print(f"AVISO: {aviso}\n")
    else:
        print("Sem sinal grosseiro de problema na divisao.")
        print("Com este n, isso significa 'sem sinal grosseiro', nao 'validado'.\n")

    print("Proximo passo: treinar SOMENTE em treino, ajustar a probabilidade em")
    print("calibracao, e tocar em teste uma unica vez, no fim.")


# ===========================================================================
def demo(n=400):
    """Dataset falso com deriva de proposito: a taxa-base sobe ao longo do tempo."""
    rng = np.random.default_rng(13)
    datas = pd.to_datetime("2020-01-01") + pd.to_timedelta(
        np.sort(rng.integers(0, 2100, n)), unit="D")
    anos = (datas.year - 2020).to_numpy()
    y = rng.random(n) < (0.35 + 0.04 * anos)
    return pd.DataFrame({
        "caso_id": [f"c{i:04d}" for i in range(n)],
        "numero_cnj": [f"{i:07d}-00.2022.5.16.0001" for i in range(n)],
        "pedido": "insalubridade",
        "data_sentenca": datas,
        "vara": rng.choice(["1a VT Balsas", "2a VT Balsas", "1a VT Imperatriz"], n),
        "y": y.astype(int),
    })


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="../data/juripredict.csv")
    ap.add_argument("--treino", type=float, default=0.60)
    ap.add_argument("--calibracao", type=float, default=0.20)
    ap.add_argument("--gravar", action="store_true",
                    help="regrava o arquivo de entrada com esta particao")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    if a.treino + a.calibracao >= 1:
        sys.exit("treino + calibracao precisa sobrar particao de teste.")

    if a.demo:
        modelo = demo()
        completo = None
    else:
        completo = pd.read_csv(a.entrada, parse_dates=["data_sentenca"])
        if "populacao" not in completo.columns:
            sys.exit(f"{a.entrada} nao tem a coluna `populacao`. "
                     f"Rode montar_dataset.py primeiro.")
        # so a populacao do modelo e particionada; escape com particao
        # convidaria a inclui-la na avaliacao
        modelo = completo[completo["populacao"] == "modelo"].copy()
        if modelo.empty:
            sys.exit("nenhuma linha com populacao == 'modelo'.")

    modelo, c1, c2, sem_data = dividir(modelo, a.treino, a.calibracao)
    relatorio(modelo, c1, c2, sem_data, a.treino, a.calibracao)

    if a.demo:
        pass
    elif a.gravar:
        completo["particao"] = pd.NA
        completo.loc[modelo.index, "particao"] = modelo["particao"]
        completo.to_csv(a.entrada, index=False)
        print(f"\n{a.entrada} regravado com esta particao.")
    else:
        print("\nNada foi gravado. A particao ja no arquivo veio do "
              "montar_dataset.py;\nuse --gravar para aplicar este corte no lugar.")
