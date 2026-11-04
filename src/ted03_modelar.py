"""TED 03: compara modelos por validação cruzada, avalia o escolhido no teste e mede a generalização.

Uso: python src/ted03_modelar.py (depois dos scripts das TEDs 01 e 02)
Saídas: resultados/ted03_resultados.json, resultados/figuras/ e o modelo em data/processed/ (fora do Git).
"""

import json
import re
import warnings
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.sparse import issparse
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import TruncatedSVD
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix,
    f1_score, log_loss,
)
from sklearn.model_selection import (
    GridSearchCV, StratifiedGroupKFold, cross_validate, learning_curve,
)
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from ted02_limpar_e_explorar import (
    CLASSES, CORES, DADOS, FIGURAS, RAIZ, RESULTADOS, TINTA, TOKEN,
    estilo, limpar_movimentacao, salvar,
)

SEMENTE = 42
JANELAS = [1, 2, 3, 5, 10, 20, 50, None]
BOOTSTRAP = 2000
# Cada processo paralelo recebe uma cópia dos dados; três cabem em uma máquina de 8 GB.
N_JOBS = 3


def tfidf(**kw):
    base = dict(token_pattern=TOKEN, lowercase=True, ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    return TfidfVectorizer(**{**base, **kw})


def lr(**kw):
    base = dict(C=10, class_weight="balanced", max_iter=3000, random_state=SEMENTE)
    return LogisticRegression(**{**base, **kw})


def janela(df, k):
    return df.movs.apply(lambda m: " ".join(m[:k] if k else m))


def com_colunas(df, k):
    """Separa a última movimentação das anteriores, para que o modelo saiba a posição do termo."""
    return pd.DataFrame({
        "ultima": df.movs.str[0],
        "anteriores": df.movs.apply(lambda m: " ".join(m[1:k]) or "vazio"),
        "log_n_mov": np.log1p(df.n_mov.values),
    }, index=df.index)


def cv_dev():
    return StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMENTE)


def avaliar_cv(modelo, X, y, grupos):
    r = cross_validate(modelo, X, y, groups=grupos, cv=cv_dev(), scoring=["f1_macro", "accuracy"],
                       return_train_score=True, n_jobs=N_JOBS)
    return {
        "f1_macro": round(float(r["test_f1_macro"].mean()), 4),
        "f1_macro_dp": round(float(r["test_f1_macro"].std()), 4),
        "acuracia": round(float(r["test_accuracy"].mean()), 4),
        "f1_macro_treino": round(float(r["train_f1_macro"].mean()), 4),
        "f1_por_dobra": [round(float(v), 4) for v in r["test_f1_macro"]],
    }


def regra(movs):
    """Linha de base sem aprendizado: palavras-chave da última movimentação, sugeridas pela EDA."""
    ultima = movs[0].lower()
    if re.search(r"provis|execu[cç][aã]o frustrada|suspens[aã]o do processo", ultima):
        return "suspenso"
    if re.search(r"arquivad|arquivamento|arquivo geral|baixa definitiva|tr[aâ]nsito em julgado", ultima):
        return "arquivado"
    return "ativo"


def metricas(y, pred):
    relatorio = classification_report(y, pred, labels=CLASSES, output_dict=True, zero_division=0)
    # Só as classes que existem no recorte: uma classe sem exemplos derrubaria a média sem motivo.
    presentes = [c for c in CLASSES if c in set(y)]
    return {
        "acuracia": round(float(accuracy_score(y, pred)), 4),
        "acuracia_balanceada": round(float(balanced_accuracy_score(y, pred)), 4),
        "f1_macro": round(float(f1_score(y, pred, average="macro", labels=presentes, zero_division=0)), 4),
        "por_classe": {c: {k: round(float(relatorio[c][k]), 4) for k in ("precision", "recall", "f1-score", "support")} for c in CLASSES},
    }


def ic_bootstrap(y, pred, alternativo=None):
    y, pred = np.asarray(y), np.asarray(pred)
    rng = np.random.default_rng(SEMENTE)
    f1s, acs, dif = [], [], []
    for _ in range(BOOTSTRAP):
        i = rng.integers(0, len(y), len(y))
        f = f1_score(y[i], pred[i], average="macro", labels=CLASSES, zero_division=0)
        f1s.append(f)
        acs.append((y[i] == pred[i]).mean())
        if alternativo is not None:
            dif.append(f - f1_score(y[i], np.asarray(alternativo)[i], average="macro", labels=CLASSES, zero_division=0))
    q = lambda v: [round(float(x), 4) for x in np.percentile(v, [2.5, 97.5])]
    saida = {"f1_macro_ic95": q(f1s), "acuracia_ic95": q(acs)}
    if dif:
        saida["ganho_f1_sobre_regra_ic95"] = q(dif)
    return saida


def calibracao(y, proba, classes, bins=10):
    pred = classes[proba.argmax(axis=1)]
    conf = proba.max(axis=1)
    acerto = pred == np.asarray(y)
    ece = 0.0
    for lo, hi in zip(np.linspace(0, 1, bins + 1)[:-1], np.linspace(0, 1, bins + 1)[1:]):
        faixa = (conf > lo) & (conf <= hi)
        if faixa.any():
            ece += faixa.mean() * abs(acerto[faixa].mean() - conf[faixa].mean())
    return round(float(ece), 4)


def fig_linha(x, series, xlabel, ylabel, nome, rotulos_x=None, ylim=None):
    fig, ax = plt.subplots(figsize=(6.8, 2.9))
    for rotulo, y, cor in series:
        ax.plot(range(len(x)), y, color=cor, linewidth=2, marker="o", markersize=5)
        ax.text(len(x) - 1 + 0.12, y[-1], rotulo, color=TINTA, va="center", fontsize=9)
    ax.set_xticks(range(len(x)), rotulos_x or x)
    ax.set_xlim(-0.2, len(x) - 1 + (1.3 if len(series) > 1 else 0.3))
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#e9e8e2", linewidth=0.7)
    ax.set_axisbelow(True)
    estilo(ax)
    salvar(fig, nome)


def fig_confusao(matriz):
    fig, ax = plt.subplots(figsize=(4.4, 3.5))
    normal = matriz / matriz.sum(axis=1, keepdims=True)
    ax.imshow(normal, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(3), CLASSES)
    ax.set_yticks(range(3), CLASSES)
    ax.set_xlabel("Classe prevista")
    ax.set_ylabel("Classe real")
    ax.xaxis.label.set_color(TINTA)
    ax.yaxis.label.set_color(TINTA)
    for i in range(3):
        for j in range(3):
            ax.text(j, i, f"{matriz[i, j]}\n{normal[i, j]:.1%}", ha="center", va="center", fontsize=9,
                    color="white" if normal[i, j] > 0.55 else "#0b0b0b")
    ax.spines[:].set_visible(False)
    ax.tick_params(length=0, colors=TINTA)
    salvar(fig, "fig_confusao.png")


def fig_coeficientes(modelo, k=10):
    pre, clf = modelo.steps[0][1], modelo.steps[-1][1]
    nomes = pre.get_feature_names_out()
    saida = {}
    fig, eixos = plt.subplots(1, 3, figsize=(9.2, 3.2))
    for ax, classe, linha in zip(eixos, clf.classes_, clf.coef_):
        topo = np.argsort(linha)[::-1][:k]
        termos = [nomes[i].replace("ultima__", "U: ").replace("anteriores__", "A: ").replace("num__", "") for i in topo]
        saida[classe] = [{"termo": t, "coef": round(float(linha[i]), 2)} for t, i in zip(termos, topo)]
        ax.barh(termos[::-1], linha[topo][::-1], color=CORES[classe], height=0.6)
        ax.set_title(classe, loc="left", fontsize=10, color="#0b0b0b")
        ax.set_xlabel("Coeficiente")
        ax.tick_params(axis="y", labelsize=8)
        estilo(ax)
    fig.tight_layout()
    salvar(fig, "fig_coeficientes.png")
    return saida


def treino_teste_externo(modelo, treino, teste, preparar):
    """Avalia em outro recorte, sem deixar a mesma janela de movimentações dos dois lados."""
    treino = treino[~treino.grupo.isin(set(teste.grupo))]
    modelo.fit(preparar(treino), treino.classe)
    saida = metricas(teste.classe, modelo.predict(preparar(teste)))
    saida["n_treino"], saida["n_teste"] = len(treino), len(teste)
    return saida


def teste_datajud(modelo, preparar):
    """Aplica o modelo a um processo real do TRT-16. Sem rótulo: é só uma checagem de vocabulário."""
    caminho = RAIZ / "dataset" / "data" / "datajud_amostra.json"
    if not caminho.exists():
        return None
    # ponytail: a amostra local tem um único processo; medir o desvio exige coletar um lote rotulado.
    processos = [json.loads(caminho.read_text(encoding="utf-8"))]
    linhas = []
    for proc in processos:
        ordenados = sorted(proc.get("movimentos") or [], key=lambda m: m.get("dataHora", ""), reverse=True)
        movs = []
        for m in ordenados:
            complementos = " ".join(c.get("nome", "") for c in m.get("complementosTabelados") or [])
            movs.append(limpar_movimentacao(f"{m.get('nome', '')} {complementos}"))
        if movs:
            linhas.append({"movs": movs, "n_mov": len(movs), "grau": proc.get("grau")})
    df = pd.DataFrame(linhas)
    proba = modelo.predict_proba(preparar(df))
    classes = modelo.steps[-1][1].classes_
    vocabulario = modelo.steps[0][1].named_transformers_["ultima"].vocabulary_
    tokens = [t for movs in df.movs for t in re.findall(TOKEN, " ".join(movs).lower())]
    return {
        "processos": len(df),
        "classes_previstas": pd.Series(classes[proba.argmax(axis=1)]).value_counts().to_dict(),
        "confianca_media": round(float(proba.max(axis=1).mean()), 3),
        "tokens_conhecidos": round(sum(t in vocabulario for t in tokens) / max(len(tokens), 1), 3),
        "casos": [
            {"grau": g, "n_mov": int(n), "ultima": m[0][:90], "prevista": str(classes[p.argmax()]), "confianca": round(float(p.max()), 3)}
            for g, n, m, p in zip(df.grau, df.n_mov, df.movs, proba)
        ],
    }


def main():
    warnings.filterwarnings("ignore", category=FutureWarning)
    df = pd.read_json(DADOS / "processed" / "processos.jsonl", lines=True, dtype={"id": str, "grupo": str})
    y, grupos = df.classe.values, df.grupo.values

    # Teste separado antes de tudo: uma dobra de cinco, sem dividir grupos e mantendo a proporção das classes.
    dev_i, teste_i = next(StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMENTE).split(df, y, grupos))
    dev, teste = df.iloc[dev_i].reset_index(drop=True), df.iloc[teste_i].reset_index(drop=True)
    assert not set(dev.grupo) & set(teste.grupo)
    y_dev, g_dev = dev.classe.values, dev.grupo.values
    df.assign(particao=np.where(df.index.isin(teste_i), "teste", "desenvolvimento"))[["id", "particao"]].to_csv(
        RESULTADOS / "ted03_particao.csv", index=False)
    r = {
        "particao": {
            "desenvolvimento": len(dev), "teste": len(teste),
            "classes_dev": dev.classe.value_counts().to_dict(), "classes_teste": teste.classe.value_counts().to_dict(),
        }
    }

    # Linhas de base
    bases = {"maioria": avaliar_cv(DummyClassifier(strategy="most_frequent"), janela(dev, 1), y_dev, g_dev)}
    pred_regra_dev = dev.movs.apply(regra)
    bases["regra"] = {
        "f1_macro": round(float(f1_score(y_dev, pred_regra_dev, average="macro")), 4),
        "acuracia": round(float(accuracy_score(y_dev, pred_regra_dev)), 4),
    }
    r["linhas_de_base_dev"] = bases

    # E1: tamanho da janela, sem informar a posição dos termos
    r["e1_janela"] = {str(k or "todas"): avaliar_cv(make_pipeline(tfidf(), lr()), janela(dev, k), y_dev, g_dev) for k in JANELAS}
    fig_linha([str(k or "todas") for k in JANELAS], [("F1 macro", [v["f1_macro"] for v in r["e1_janela"].values()], CORES["arquivado"])],
              "Últimas movimentações usadas", "F1 macro (validação cruzada)", "fig_janela.png")

    # E2: informação contida em cada posição isolada
    r["e2_posicao"] = {}
    for p in range(1, 11):
        tem = dev.n_mov >= p
        X = dev.movs[tem].apply(lambda m: m[p - 1])
        r["e2_posicao"][str(p)] = {**avaliar_cv(make_pipeline(tfidf(), lr()), X, y_dev[tem], g_dev[tem]), "n": int(tem.sum())}
    fig_linha(list(r["e2_posicao"]), [("F1 macro", [v["f1_macro"] for v in r["e2_posicao"].values()], CORES["arquivado"])],
              "Posição da movimentação (1 = a mais recente)", "F1 macro usando só essa posição", "fig_posicao.png", ylim=(0, 1))

    # E3: algoritmos na janela de 5, a mesma do artigo original
    X5 = janela(dev, 5)
    algoritmos = {
        "Naive Bayes complementar": make_pipeline(tfidf(), ComplementNB()),
        "SVM linear": make_pipeline(tfidf(), LinearSVC(C=1, class_weight="balanced", random_state=SEMENTE)),
        "Regressão logística": make_pipeline(tfidf(), lr()),
        "Gradient boosting + SVD": make_pipeline(
            tfidf(), TruncatedSVD(200, random_state=SEMENTE),
            HistGradientBoostingClassifier(class_weight="balanced", random_state=SEMENTE)),
    }
    r["e3_algoritmos"] = {n: avaliar_cv(m, X5, y_dev, g_dev) for n, m in algoritmos.items()}

    # E4: posição dos termos e tamanho do histórico
    def preprocessador(numerico=True):
        partes = [("ultima", tfidf(), "ultima"), ("anteriores", tfidf(), "anteriores")]
        if numerico:
            partes.append(("num", StandardScaler(), ["log_n_mov"]))
        return ColumnTransformer(partes)

    Xc = com_colunas(dev, 5)
    r["e4_atributos"] = {
        "janela 5, sem posição": r["e3_algoritmos"]["Regressão logística"],
        "última + 4 anteriores": avaliar_cv(make_pipeline(preprocessador(False), lr()), Xc, y_dev, g_dev),
        "última + 4 anteriores + log(n_mov)": avaliar_cv(make_pipeline(preprocessador(True), lr()), Xc, y_dev, g_dev),
    }

    # E5: IDF e vocabulário aprendidos nos textos sem rótulo
    sem_rotulo = (DADOS / "processed" / "sem_rotulo_limpo.txt").read_text(encoding="utf-8").split("\n")
    vetor_externo = tfidf(min_df=5, max_features=200000).fit(sem_rotulo)
    del sem_rotulo
    X_ext = vetor_externo.transform(X5)
    r["e5_sem_rotulo"] = {
        "n_atributos": X_ext.shape[1],
        **avaliar_cv(lr(), X_ext, y_dev, g_dev),
    }

    # E6: ajuste de hiperparâmetros do melhor arranjo
    busca = GridSearchCV(
        make_pipeline(preprocessador(False), lr()),
        {
            "logisticregression__C": [1, 3, 10, 30, 100],
            "logisticregression__class_weight": ["balanced", None],
            "columntransformer__ultima__ngram_range": [(1, 1), (1, 2)],
        },
        scoring="f1_macro", cv=cv_dev(), n_jobs=N_JOBS, refit=True,
    )
    busca.fit(Xc, y_dev, groups=g_dev)
    r["e5_sem_rotulo"]["ganho_por_dobra_sobre_ultima_mais_anteriores"] = [
        round(a - b, 4) for a, b in zip(r["e5_sem_rotulo"]["f1_por_dobra"], r["e4_atributos"]["última + 4 anteriores"]["f1_por_dobra"])
    ]
    r["e6_busca"] = {
        "melhores": {k.split("__", 1)[-1]: str(v) for k, v in busca.best_params_.items()},
        "f1_macro": round(float(busca.best_score_), 4),
        "f1_macro_dp": round(float(busca.cv_results_["std_test_score"][busca.best_index_]), 4),
        "combinacoes": len(busca.cv_results_["params"]),
    }
    modelo = busca.best_estimator_
    r["ajuste_final"] = {"f1_macro_treino": round(float(f1_score(y_dev, modelo.predict(Xc), average="macro")), 4)}

    # Curva de aprendizado
    tamanhos, tr, va = learning_curve(
        make_pipeline(preprocessador(False), lr()).set_params(**busca.best_params_), Xc, y_dev, groups=g_dev,
        cv=cv_dev(), scoring="f1_macro", train_sizes=[0.1, 0.25, 0.5, 0.75, 1.0], n_jobs=N_JOBS)
    r["curva_aprendizado"] = {
        "tamanhos": [int(t) for t in tamanhos],
        "treino": [round(float(v), 4) for v in tr.mean(axis=1)],
        "validacao": [round(float(v), 4) for v in va.mean(axis=1)],
    }
    fig_linha([int(t) for t in tamanhos], [("treino", tr.mean(axis=1), CORES["ativo"]), ("validação", va.mean(axis=1), CORES["arquivado"])],
              "Processos usados no treino", "F1 macro", "fig_aprendizado.png", ylim=(0.7, 1.02))

    # Avaliação final: o teste só é usado aqui, com o modelo já escolhido
    Xt = com_colunas(teste, 5)
    y_t = teste.classe.values
    proba = modelo.predict_proba(Xt)
    classes = modelo.steps[-1][1].classes_
    pred = classes[proba.argmax(axis=1)]
    pred_regra = teste.movs.apply(regra).values
    matriz = confusion_matrix(y_t, pred, labels=CLASSES)
    fig_confusao(matriz)
    r["teste"] = {
        "modelo": {**metricas(y_t, pred), **ic_bootstrap(y_t, pred, pred_regra)},
        "regra": {**metricas(y_t, pred_regra), **ic_bootstrap(y_t, pred_regra)},
        "maioria": metricas(y_t, np.full(len(y_t), "arquivado")),
        "matriz_confusao": matriz.tolist(),
        "log_loss": round(float(log_loss(y_t, proba, labels=classes)), 4),
        "ece": calibracao(y_t, proba, classes),
    }

    # Abstenção: até onde a confiança separa os casos que podem dispensar a conferência
    conf = proba.max(axis=1)
    r["abstencao"] = []
    for limiar in [0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]:
        aceitos = conf >= limiar
        r["abstencao"].append({
            "limiar": limiar, "cobertura": round(float(aceitos.mean()), 4), "n": int(aceitos.sum()),
            "acuracia": round(float((pred[aceitos] == y_t[aceitos]).mean()), 4),
            "f1_macro": round(float(f1_score(y_t[aceitos], pred[aceitos], average="macro", labels=CLASSES, zero_division=0)), 4),
        })
    fig_linha([f"{a['limiar']:.0%}" if a["limiar"] else "sem corte" for a in r["abstencao"]],
              [("acurácia", [a["acuracia"] for a in r["abstencao"]], CORES["arquivado"]),
               ("cobertura", [a["cobertura"] for a in r["abstencao"]], CORES["ativo"])],
              "Confiança mínima para aceitar a previsão", "Proporção do conjunto de teste", "fig_abstencao.png", ylim=(0, 1.03))

    # Onde o modelo erra
    ultima = teste.movs.str[0].str.lower()
    grupos_erro = {
        "sentença na última": ultima.str.contains(r"senten[cç]a"),
        "certidão de publicação na última": ultima.str.contains(r"certid[aã]o de publica"),
        "menos de 5 movimentações": teste.n_mov < 5,
        "origem RJ (provável)": teste.origem == "RJ (provável)",
        "origem SP (provável)": teste.origem == "SP (provável)",
    }
    r["erros"] = {
        "total": int((pred != y_t).sum()),
        "ativo_previsto_como_arquivado": int(((y_t == "ativo") & (pred == "arquivado")).sum()),
        "recortes": {
            n: {"n": int(m.sum()), "taxa_erro": round(float((pred[m.values] != y_t[m.values]).mean()), 4) if m.any() else None}
            for n, m in grupos_erro.items()
        },
    }
    r["coeficientes"] = fig_coeficientes(modelo)
    # Auditoria manual de nomes residuais: fica fora do Git, junto com os dados.
    nomes = modelo.steps[0][1].get_feature_names_out()
    clf = modelo.steps[-1][1]
    (DADOS / "processed" / "auditoria_coeficientes.txt").write_text(
        "\n".join(f"{c}\t{nomes[i]}\t{l[i]:.2f}" for c, l in zip(clf.classes_, clf.coef_) for i in np.argsort(l)[::-1][:150]),
        encoding="utf-8")

    # Generalização: outro tribunal e outro período, com os hiperparâmetros já fixados
    fabrica = lambda: make_pipeline(preprocessador(False), lr()).set_params(**busca.best_params_)
    prep = lambda d: com_colunas(d, 5)
    sp, rj = df[df.origem == "SP (provável)"], df[df.origem == "RJ (provável)"]
    com_ano = df[df.ano_ref.notna()]
    r["generalizacao"] = {
        "treino SP -> teste RJ": treino_teste_externo(fabrica(), sp, rj, prep),
        "treino RJ -> teste SP": treino_teste_externo(fabrica(), rj, sp, prep),
        "treino ate 2017 -> teste 2018-2019": treino_teste_externo(
            fabrica(), com_ano[com_ano.ano_ref <= 2017], com_ano[com_ano.ano_ref.isin([2018, 2019])], prep),
        "treino ate 2018 -> teste 2019": treino_teste_externo(
            fabrica(), com_ano[com_ano.ano_ref <= 2018], com_ano[com_ano.ano_ref == 2019], prep),
    }
    r["datajud"] = teste_datajud(modelo, prep)

    joblib.dump(modelo, DADOS / "processed" / "modelo_status.joblib")
    (RESULTADOS / "ted03_resultados.json").write_text(json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(r, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
