"""TED 02: limpa a base rotulada e produz as estatísticas e os gráficos da análise exploratória.

Uso: python src/ted02_limpar_e_explorar.py (depois do script da TED 01)
Saídas: data/processed/processos.jsonl (com texto, fora do Git) e resultados/ (sem texto).
"""

import csv
import hashlib
import json
import mmap
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.feature_selection import chi2

RAIZ = Path(__file__).resolve().parent.parent
DADOS = Path(os.environ.get("DADOS_DIR", RAIZ / "data"))
RESULTADOS = RAIZ / "resultados"
FIGURAS = RESULTADOS / "figuras"

CLASSES = ["arquivado", "ativo", "suspenso"]
CORES = {"arquivado": "#2a78d6", "ativo": "#eb6834", "suspenso": "#1baf7a"}
TINTA = "#52514e"
ANO_MIN, ANO_MAX = 1990, 2021  # a base foi publicada em maio de 2021
LIMITE_CHARS = 2000  # próximo do percentil 99 do tamanho das movimentações
JANELA = 5  # últimas movimentações que identificam casos praticamente iguais
TOKEN = r"(?u)\b[^\W\d_]{2,}\b"

MASCARAS = [
    ("tkcnj", re.compile(r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b")),
    ("tkdoc", re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")),
    ("tkoab", re.compile(r"\bOAB[\s/:.-]*[A-Z]{0,2}[\s/:.-]*\d[\d.]*(?:[\s/-]*[A-Z]{2})?", re.I)),
    ("tkemail", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("tkvalor", re.compile(r"R\$\s*[\d.,]+")),
    ("tkdata", re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")),
    ("tknum", re.compile(r"\b\d[\d./-]*\b")),
]
DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
PREFIXO_CAMPOS = "Tipo do Movimento:"
CONTROLE = re.compile(r"[\x00-\x1f\x7f-\x9f]+")
ESPACOS = re.compile(r"\s+")
PALAVRA = re.compile(r"[^\W\d_]+")
MAIUSCULA = r"[A-ZÀ-Ý][\w'’.-]*"
SEQUENCIA_NOME = rf"{MAIUSCULA}(?:\s+(?:(?:de|da|do|dos|das|e|D[aeo]s?)\s+)?{MAIUSCULA})*"
# Nomes aparecem antes do número da OAB ou depois de quem é a pessoa no processo.
SEQUENCIA = re.compile(SEQUENCIA_NOME)
PAR_JSON = re.compile(rb'"(?:[^"\\]|\\.)*":\s*("(?:[^"\\]|\\.)*")')
NOME_ANTES_OAB = re.compile(rf"({SEQUENCIA_NOME})[\s,(-]*OAB\b")
NOME_APOS_PAPEL = re.compile(
    rf"\b(?i:parte|autora?|r[ée]u|r[ée]|exequente|executad[oa]|requerente|requerid[oa]|advogad[oa]s?(?:\(s\))?"
    rf"|dra?\.?|ju[ií]za?)\s*:?\s+({SEQUENCIA_NOME})")
# Órgãos, siglas e termos de sistema que vêm sempre em maiúscula, mas não são nomes de pessoa.
NAO_NOMES = frozenset("""
    advogada advogado advogados bacenjud brasil câmara cep cível cnpj colégio corregedoria cpc cpf csm defensoria
    del depre descrição diário disponibilização diversas djerj dje egrégio fazenda ffpa fesp fórum imesc inss
    instaurado int interna intermediária iii juiz juíza juizado judiciário ltda ministério ministro movimento ncpc
    número oab página praticado procuradoria proger publicável regional reprografia restrito rio saj seq sidap
    situacão sorteio status stf stj supremo tribunal turma vara wfpa wjmj
    adi cdc cejusc comercio conselho cump deecrim delegacia desembargador dju empreendimentos fedtj infância ipesp
    oja presidente república secretaria spprev sucessões viii vossa
    advogadoadvogado agrg câm câmaras cidadania colendo cpp digitados dpvat iirgd júri nscgj prog reativados xiv xvi
""".split())
# Sobrenomes achados na auditoria dos termos de maior peso do modelo. Também são palavras comuns
# em minúscula, por isso o filtro do léxico os rejeita.
SOBRENOMES_AUDITADOS = frozenset("angelo guerra parada paula sá vintena".split())


def textos_json_plano(caminho):
    """Percorre os valores de um JSON {id: texto} sem carregar o arquivo inteiro na memória."""
    with open(caminho, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as dados:
        for par in PAR_JSON.finditer(dados):
            yield json.loads(par[1])


def normalizar(texto):
    """Unifica a codificação (o NBSP vira espaço) e remove quebras e caracteres de controle."""
    texto = unicodedata.normalize("NFKC", texto or "")
    return ESPACOS.sub(" ", CONTROLE.sub(" ", texto)).strip()


def mascarar(texto, contagem=None):
    for marca, padrao in MASCARAS:
        texto, n = padrao.subn(marca, texto)
        if contagem is not None:
            contagem[marca] += n
    return texto


def construir_lexico(textos):
    """Palavras usadas como nome de pessoa e que quase nunca aparecem em minúscula.

    A segunda condição preserva termos jurídicos capturados por engano. Palavras que abrem
    movimentações (Despacho, Decisão) também ficam de fora, porque nomeiam o tipo do ato.
    Uma segunda passada (por isso `textos` precisa ser uma lista) acrescenta as palavras coladas
    a um nome já conhecido, como sobrenomes que nunca aparecem junto da OAB.
    ponytail: heurística; nome isolado de qualquer outro nome conhecido escapa.
    Se isso pesar, trocar por um reconhecedor de entidades treinado em textos jurídicos.
    """
    candidatos, minusculas, maiusculas, iniciais = Counter(), Counter(), Counter(), Counter()

    def limpo(bruto):
        # O limite é o mesmo da limpeza: o que passa dele não chega à base tratada.
        return normalizar(bruto).removeprefix(PREFIXO_CAMPOS).strip()[:LIMITE_CHARS]

    for bruto in textos:
        texto = limpo(bruto)
        for padrao in (NOME_ANTES_OAB, NOME_APOS_PAPEL) if "OAB" in texto else (NOME_APOS_PAPEL,):
            for trecho in padrao.findall(texto):
                candidatos.update(p.lower() for p in PALAVRA.findall(trecho) if len(p) >= 3)
        palavras = PALAVRA.findall(texto)
        if palavras:
            iniciais[palavras[0].lower()] += 1
        for p in palavras:
            (maiusculas if p[0].isupper() else minusculas)[p.lower()] += 1

    def aceita(p):
        return p not in NAO_NOMES and minusculas[p] < 0.02 * maiusculas[p] and iniciais[p] < 0.02 * maiusculas[p]

    lexico = {p for p in candidatos if aceita(p)}
    vizinhos = set()
    for bruto in textos:
        for trecho in SEQUENCIA.findall(limpo(bruto)):
            palavras = [p.lower() for p in PALAVRA.findall(trecho) if len(p) >= 3]
            if len(palavras) > 1 and not lexico.isdisjoint(palavras):
                vizinhos.update(palavras)
    return lexico | {p for p in vizinhos if aceita(p)} | SOBRENOMES_AUDITADOS


def mascarar_nomes(texto, lexico, contagem=None):
    def trocar(m):
        return "tknome" if m[0][0].isupper() and m[0].lower() in lexico else m[0]

    texto = re.sub(r"tknome(?:\s+(?:(?:de|da|do|dos|das|e)\s+)?tknome)+", "tknome", PALAVRA.sub(trocar, texto))
    if contagem is not None:
        contagem["tknome"] += sum(1 for p in PALAVRA.findall(texto) if p == "tknome")
    return texto


def limpar_movimentacao(texto, contagem=None, lexico=frozenset()):
    texto = normalizar(texto)
    if texto.startswith(PREFIXO_CAMPOS):
        texto = texto[len(PREFIXO_CAMPOS):].strip()
    return mascarar(mascarar_nomes(texto, lexico, contagem), contagem)[:LIMITE_CHARS]


def ano_referencia(textos_recentes):
    """Maior ano válido entre as datas citadas; datas impossíveis ou futuras são ignoradas."""
    anos = [
        int(a)
        for t in textos_recentes
        for d, m, a in DATA.findall(t)
        if 1 <= int(d) <= 31 and 1 <= int(m) <= 12 and ANO_MIN <= int(a) <= ANO_MAX
    ]
    return max(anos) if anos else None


def preparar(bruto, lexico):
    contagem = Counter()
    linhas = []
    for pid, proc in bruto.items():
        # A chave -1 é a movimentação mais recente, -2 a anterior, e assim por diante.
        ordem = sorted(proc["texts"], key=lambda k: -int(k))
        originais = [proc["texts"][k] for k in ordem]
        contagem["com_nbsp_ou_controle"] += sum(
            1 for t in originais if "\xa0" in t or CONTROLE.search(t)
        )
        contagem["acima_do_limite"] += sum(1 for t in originais if len(normalizar(t)) > LIMITE_CHARS)
        contagem["com_ano_invalido"] += sum(
            1 for t in originais
            for d, m, a in DATA.findall(t)
            if not (1 <= int(d) <= 31 and 1 <= int(m) <= 12 and ANO_MIN <= int(a) <= ANO_MAX)
        )
        n_campos = sum(1 for t in originais if t.startswith(PREFIXO_CAMPOS))
        movs = [limpar_movimentacao(t, contagem, lexico) for t in originais]
        contagem["vazias_apos_limpeza"] += sum(1 for m in movs if not m)
        contagem["repetidas_em_sequencia"] += sum(1 for a, b in zip(movs, movs[1:]) if a == b)
        janela = " | ".join(movs[:JANELA]).lower()
        linhas.append({
            "id": pid,
            "classe": proc["label"].removeprefix("H:").lower(),
            "origem": "RJ (provável)" if n_campos > len(originais) / 2 else "SP (provável)",
            "ano_ref": ano_referencia(originais[:10]),
            "n_mov": len(movs),
            "chars_total": sum(len(m) for m in movs),
            "chars_medio": round(sum(len(m) for m in movs) / len(movs), 1),
            "grupo": hashlib.sha1(janela.encode()).hexdigest()[:16],
            "movs": movs,
        })
    return linhas, contagem


def remover_duplicados(linhas):
    vistos, unicos = set(), []
    for linha in linhas:
        chave = (linha["classe"], tuple(linha["movs"]))
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(linha)
    return unicos


def estilo(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#c9c8c2")
    ax.tick_params(colors=TINTA, length=0)
    ax.xaxis.label.set_color(TINTA)
    ax.yaxis.label.set_color(TINTA)


def salvar(fig, nome):
    FIGURAS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURAS / nome, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fig_classes_origem(df):
    fig, eixos = plt.subplots(1, 2, figsize=(8.6, 2.6), sharex=False, gridspec_kw={"wspace": 0.42})
    for ax, origem in zip(eixos, ["SP (provável)", "RJ (provável)"]):
        parte = df[df.origem == origem]
        fatias = parte.classe.value_counts().reindex(CLASSES).fillna(0)
        ax.barh(CLASSES[::-1], fatias[CLASSES[::-1]], color=[CORES[c] for c in CLASSES[::-1]], height=0.55)
        for i, c in enumerate(CLASSES[::-1]):
            ax.text(fatias[c], i, f"  {int(fatias[c])} ({fatias[c] / len(parte):.1%})", va="center", color=TINTA, fontsize=9)
        ax.set_title(f"{origem}: {len(parte)} processos", loc="left", fontsize=10, color="#0b0b0b")
        ax.set_xlim(0, fatias.max() * 1.5)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        estilo(ax)
    salvar(fig, "fig_classes_origem.png")


def fig_n_mov(df):
    fig, ax = plt.subplots(figsize=(7, 2.8))
    dados = [df.loc[df.classe == c, "n_mov"] for c in CLASSES[::-1]]
    caixa = ax.boxplot(dados, vert=False, widths=0.5, patch_artist=True, tick_labels=CLASSES[::-1],
                       flierprops={"marker": "o", "markersize": 2, "alpha": 0.25, "markeredgecolor": TINTA},
                       medianprops={"color": "#0b0b0b", "linewidth": 1.5})
    for patch, c in zip(caixa["boxes"], CLASSES[::-1]):
        patch.set(facecolor=CORES[c], alpha=0.75, edgecolor=TINTA)
    ax.set_xscale("log")
    ax.set_xlabel("Movimentações por processo (escala logarítmica)")
    ax.grid(axis="x", color="#e9e8e2", linewidth=0.7)
    ax.set_axisbelow(True)
    estilo(ax)
    salvar(fig, "fig_n_mov.png")


def fig_anos(df):
    anos = list(range(2013, 2020))
    tabela = df[df.ano_ref.isin(anos)].groupby(["ano_ref", "classe"]).size().unstack(fill_value=0).reindex(columns=CLASSES)
    fatias = tabela.div(tabela.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(7, 3))
    # Rótulos no fim das linhas, afastados quando os valores do último ano ficam próximos.
    altura = {}
    for c in sorted(CLASSES, key=lambda c: fatias[c].iloc[-1]):
        altura[c] = max(fatias[c].iloc[-1] * 100, max(altura.values(), default=-100) + 7)
    for c in CLASSES:
        ax.plot(fatias.index, fatias[c] * 100, color=CORES[c], linewidth=2, marker="o", markersize=5)
        ax.text(fatias.index[-1] + 0.08, altura[c], c, color=TINTA, va="center", fontsize=9)
    ax.set_xticks(anos, [f"{a}\nn={int(tabela.loc[a].sum())}" for a in anos])
    ax.set_xlim(2012.8, 2019.9)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% dos processos do ano")
    ax.grid(axis="y", color="#e9e8e2", linewidth=0.7)
    ax.set_axisbelow(True)
    estilo(ax)
    salvar(fig, "fig_anos.png")
    return tabela


def fig_expressoes(df):
    padroes = {
        "arquivado definitivamente": r"arquivad[oa] definitiv",
        "baixa definitiva": r"baixa definitiva",
        "trânsito em julgado": r"tr[aâ]nsito em julgado",
        "arquivado/arquivamento provisório": r"arquivad[oa] provis|arquivamento provis",
        "suspensão do prazo": r"suspens[aã]o do prazo",
        "sentença": r"senten[cç]a",
        "conclusos": r"conclusos",
        "certidão de publicação": r"certid[aã]o de publica",
    }
    ultima = df.movs.str[0]
    linhas, proporcoes = [], []
    for rotulo, padrao in padroes.items():
        marcados = df[ultima.str.contains(padrao, case=False, regex=True)]
        cont = marcados.classe.value_counts().reindex(CLASSES).fillna(0).astype(int)
        linhas.append({"expressao": rotulo, "n": int(cont.sum()), **cont.to_dict()})
        proporcoes.append((cont / max(cont.sum(), 1)).values)
    matriz = np.array(proporcoes)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.imshow(matriz, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(3), CLASSES)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(linhas)), [f"{l['expressao']} (n={l['n']})" for l in linhas])
    for i in range(matriz.shape[0]):
        for j in range(3):
            ax.text(j, i, f"{matriz[i, j]:.0%}", ha="center", va="center", fontsize=9,
                    color="white" if matriz[i, j] > 0.55 else "#0b0b0b")
    ax.spines[:].set_visible(False)
    ax.tick_params(length=0, colors=TINTA)
    salvar(fig, "fig_expressoes.png")
    return linhas


def termos_discriminantes(df, k=10):
    textos = df.movs.apply(lambda m: " ".join(m[:JANELA]))
    cv = CountVectorizer(binary=True, min_df=20, token_pattern=TOKEN, lowercase=True)
    X = cv.fit_transform(textos)
    nomes = np.array(cv.get_feature_names_out())
    # Só mantemos termos que aparecem em muitos processos: nomes de pessoas não chegam aqui.
    resultado = {}
    fig, eixos = plt.subplots(1, 3, figsize=(9, 3.2))
    for ax, c in zip(eixos, CLASSES):
        y = (df.classe == c).values
        score, _ = chi2(X, y)
        taxa_in = np.asarray(X[y].mean(axis=0)).ravel()
        taxa_out = np.asarray(X[~y].mean(axis=0)).ravel()
        score = np.where(taxa_in > taxa_out, score, 0)
        topo = np.argsort(score)[::-1][:k]
        resultado[c] = [{"termo": nomes[i], "chi2": round(float(score[i]), 1)} for i in topo]
        ax.barh(nomes[topo][::-1], score[topo][::-1], color=CORES[c], height=0.6)
        ax.set_title(c, loc="left", fontsize=10, color="#0b0b0b")
        ax.set_xlabel("χ²")
        ax.tick_params(axis="y", labelsize=8)
        estilo(ax)
    fig.tight_layout()
    salvar(fig, "fig_termos.png")
    return resultado


def resumo_sem_rotulo(df, frequencia, lexico):
    """Limpa os textos sem rótulo e mede a sobreposição com a base rotulada."""
    unicos = {limpar_movimentacao(t, lexico=lexico) for t in frequencia}
    unicos.discard("")
    (DADOS / "processed" / "sem_rotulo_limpo.txt").write_text("\n".join(sorted(unicos)), encoding="utf-8")
    rotuladas = Counter(m for movs in df.movs for m in movs)
    em_comum = sum(n for m, n in rotuladas.items() if m in unicos)
    mais_comuns = sum(n for _, n in frequencia.most_common(100))
    return {
        "movimentacoes": frequencia.total(),
        "textos_distintos_brutos": len(frequencia),
        "textos_distintos_limpos": len(unicos),
        "vazios": frequencia.get("", 0),
        "fatia_dos_100_textos_mais_comuns": round(mais_comuns / frequencia.total(), 4),
        "fatia_rotulada_presente_no_sem_rotulo": round(em_comum / sum(rotuladas.values()), 4),
    }


def main():
    rotulado = json.loads((DADOS / "raw" / "labeled.json").read_text(encoding="utf-8"))
    sem_rotulo = Counter(textos_json_plano(DADOS / "raw" / "unlabeled.json"))
    lexico = construir_lexico([m for p in rotulado.values() for m in p["texts"].values()] + list(sem_rotulo))
    linhas, contagem = preparar(rotulado, lexico)
    del rotulado
    n_bruto = len(linhas)
    linhas = remover_duplicados(linhas)
    (DADOS / "processed").mkdir(parents=True, exist_ok=True)
    (DADOS / "processed" / "lexico_nomes.txt").write_text("\n".join(sorted(lexico)), encoding="utf-8")
    with open(DADOS / "processed" / "processos.jsonl", "w", encoding="utf-8") as f:
        for linha in linhas:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")

    df = pd.DataFrame(linhas)
    FIGURAS.mkdir(parents=True, exist_ok=True)
    metadados = df.drop(columns="movs")
    metadados.to_csv(RESULTADOS / "ted02_base_tratada_metadados.csv", index=False, quoting=csv.QUOTE_MINIMAL)

    grupos = df.groupby("grupo").classe.agg(["size", "nunique"])
    numericas = ["n_mov", "chars_total", "chars_medio", "ano_ref"]
    por_classe = df.groupby("classe")[numericas].describe().round(1)
    kruskal = {}
    for v in ["n_mov", "chars_total", "chars_medio"]:
        h, p = stats.kruskal(*[df.loc[df.classe == c, v] for c in CLASSES])
        kruskal[v] = {"H": round(float(h), 1), "p": float(p), "eta2": round(float((h - 2) / (len(df) - 3)), 4)}
    tab = pd.crosstab(df.origem, df.classe)
    qui, p, _, _ = stats.chi2_contingency(tab)

    anos = fig_anos(df)
    resumo = {
        "processos_brutos": n_bruto,
        "duplicados_removidos": n_bruto - len(df),
        "processos_finais": len(df),
        "movimentacoes_finais": int(df.n_mov.sum()),
        "problemas": dict(contagem),
        "palavras_no_lexico_de_nomes": len(lexico),
        "classes": df.classe.value_counts().to_dict(),
        "origem_x_classe": tab.to_dict(),
        "cramer_v_origem_classe": round(float(np.sqrt(qui / (tab.values.sum() * (min(tab.shape) - 1)))), 3),
        "p_origem_classe": float(p),
        "sem_ano_ref": int(df.ano_ref.isna().sum()),
        "ano_ref_contagem": df.ano_ref.value_counts().sort_index().to_dict(),
        "processos_com_menos_de_5_mov": int((df.n_mov < JANELA).sum()),
        "grupos_janela": {
            "grupos": len(grupos),
            "grupos_repetidos": int((grupos["size"] > 1).sum()),
            "processos_em_grupos_repetidos": int(grupos.loc[grupos["size"] > 1, "size"].sum()),
            "grupos_com_rotulos_divergentes": int((grupos["nunique"] > 1).sum()),
            "processos_em_grupos_divergentes": int(grupos.loc[grupos["nunique"] > 1, "size"].sum()),
        },
        "descritivas_por_classe": {f"{a}|{b}": v for (a, b), v in por_classe.to_dict().items()},
        "descritivas_gerais": df[numericas].describe().round(1).to_dict(),
        "percentis_n_mov": df.n_mov.quantile([0.01, 0.25, 0.5, 0.75, 0.95, 0.99]).to_dict(),
        "kruskal_wallis": kruskal,
        "spearman": df[numericas].corr(method="spearman").round(3).to_dict(),
        "anos_x_classe": {int(a): v for a, v in anos.to_dict("index").items()},
        "expressoes_ultima_mov": fig_expressoes(df),
        "termos": termos_discriminantes(df),
        "sem_rotulo": resumo_sem_rotulo(df, sem_rotulo, lexico),
    }
    fig_classes_origem(df)
    fig_n_mov(df)
    (RESULTADOS / "ted02_resumo.json").write_text(json.dumps(resumo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in resumo.items() if k not in ("descritivas_por_classe",)}, indent=1, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
