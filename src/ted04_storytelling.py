"""TED 04: redesenha os resultados principais como gráficos explicativos para o Data Storytelling.

Uso: python src/ted04_storytelling.py (depois da TED 03; lê apenas resultados/*.json)
Saídas: resultados/figuras/ted04_*.png e resultados/ted04_numeros.json.

Os gráficos seguem a comunicação analítica da disciplina: título que afirma, uma cor de
destaque para a mensagem, contexto em cinza, rótulos diretos no lugar de legenda e eixo
declarado no subtítulo. Nenhum número é recalculado a partir dos dados: tudo vem dos
arquivos gravados pelas TEDs 02 e 03.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

RAIZ = Path(__file__).resolve().parents[1]
RESULTADOS = RAIZ / "resultados"
FIGURAS = RESULTADOS / "figuras"

DESTAQUE = "#2a78d6"  # a mensagem
ALERTA = "#eb6834"  # o risco
CINZA = "#a3a29b"  # o contexto
CINZA_CLARO = "#d9d8d2"
TINTA = "#52514e"
ESCURO = "#0b0b0b"


def num(v, casas=3):
    """Número no formato brasileiro."""
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def titulo(ax, frase, subtitulo):
    ax.set_title(frase, loc="left", fontsize=12, fontweight="bold", color=ESCURO, pad=26)
    ax.text(0, 1.035, subtitulo, transform=ax.transAxes, color=TINTA, fontsize=9.5)


def limpar(ax, manter=("bottom",)):
    for lado in ("top", "right", "left", "bottom"):
        ax.spines[lado].set_visible(lado in manter)
        ax.spines[lado].set_color(CINZA_CLARO)
    ax.tick_params(colors=TINTA, length=0)


def salvar(fig, nome):
    FIGURAS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURAS / nome, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def por_mil(partes, total):
    """Arredonda contagens para 'a cada mil' sem perder unidades (maior resto)."""
    brutos = [1000 * p / total for p in partes]
    base = [int(b) for b in brutos]
    falta = 1000 - sum(base)
    ordem = sorted(range(len(brutos)), key=lambda i: brutos[i] - base[i], reverse=True)
    for i in ordem[:falta]:
        base[i] += 1
    return base


def fig_janela(r):
    rotulos = ["1", "2", "3", "5", "10", "20", "50", "todas"]
    f1 = [r["e1_janela"][k]["f1_macro"] for k in rotulos]
    regra = r["linhas_de_base_dev"]["regra"]["f1_macro"]
    x = range(len(rotulos))
    fig, ax = plt.subplots(figsize=(8, 3.9))
    ax.axhline(regra, color=CINZA, linestyle=(0, (4, 3)), linewidth=1.2)
    ax.text(2.1, regra - 0.012, f"regra de palavras-chave: {num(regra)}", color=TINTA, fontsize=9,
            ha="left", va="top")
    ax.plot(x, f1, color=CINZA, linewidth=2, marker="o", markersize=6, zorder=2)
    melhor = rotulos.index("5")
    ax.plot([melhor], [f1[melhor]], marker="o", markersize=10, color=DESTAQUE, zorder=3)
    ax.annotate(f"{num(f1[melhor])} com as 5 últimas", (melhor, f1[melhor]), xytext=(0, 12),
                textcoords="offset points", ha="center", color=DESTAQUE, fontsize=10, fontweight="bold")
    ax.annotate(f"{num(f1[0])}\nsó a última", (0, f1[0]), xytext=(10, -4), textcoords="offset points",
                ha="left", va="top", color=TINTA, fontsize=9)
    ax.annotate(f"{num(f1[-1])}\nhistórico inteiro", (len(rotulos) - 1, f1[-1]), xytext=(-10, -6),
                textcoords="offset points", ha="right", va="top", color=TINTA, fontsize=9)
    ax.set_xticks(list(x), rotulos)
    ax.set_xlabel("Últimas movimentações lidas pelo modelo", color=TINTA)
    ax.set_ylim(0.5, 1.0)
    ax.set_yticks([0.5, 0.6, 0.7, 0.8, 0.9, 1.0], [num(v, 1) for v in [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]])
    ax.grid(axis="y", color="#eeede8", linewidth=0.7)
    ax.set_axisbelow(True)
    limpar(ax)
    titulo(ax, "Cinco movimentações bastam; o histórico inteiro piora o modelo",
           "F1 macro na validação cruzada (5 dobras, 5.090 processos). O eixo começa em 0,5.")
    salvar(fig, "ted04_janela.png")


def fig_regra_modelo(r):
    classes = ["arquivado", "ativo", "suspenso"]
    regra = [100 * r["teste"]["regra"]["por_classe"][c]["recall"] for c in classes]
    modelo = [100 * r["teste"]["modelo"]["por_classe"][c]["recall"] for c in classes]
    casos = [int(r["teste"]["modelo"]["por_classe"][c]["support"]) for c in classes]
    fig, ax = plt.subplots(figsize=(8, 3.3))
    y = [2, 1, 0]
    for yi, a, b in zip(y, regra, modelo):
        a, b = round(a, 1), round(b, 1)
        ganho = round(b - a, 1)
        cor = DESTAQUE if ganho > 1 else CINZA
        ax.plot([a, b], [yi, yi], color=CINZA_CLARO, linewidth=5, solid_capstyle="round", zorder=1)
        ax.scatter([a], [yi], s=90, color=CINZA, zorder=2)
        ax.scatter([b], [yi], s=110, color=cor, zorder=3)
        sinal = "+" if ganho >= 0 else "−"
        texto = f"{sinal}{num(abs(ganho), 1)} p.p."
        if ganho > 1:
            ax.text(a - 2, yi, f"regra {num(a, 1)}%", ha="right", va="center", color=TINTA, fontsize=9)
            ax.text(b + 2, yi, f"modelo {num(b, 1)}%  ({texto})", ha="left", va="center",
                    color=DESTAQUE, fontsize=9.5, fontweight="bold")
        else:
            ax.text(min(a, b) - 2, yi, f"regra {num(a, 1)}% · modelo {num(b, 1)}%  ({texto})",
                    ha="right", va="center", color=TINTA, fontsize=9)
    ax.set_yticks(y, [f"{c}\n({n} casos)" for c, n in zip(classes, casos)])
    ax.set_xlim(20, 130)
    ax.set_xticks([20, 40, 60, 80, 100], ["20%", "40%", "60%", "80%", "100%"])
    ax.set_ylim(-0.6, 2.6)
    ax.grid(axis="x", color="#eeede8", linewidth=0.7)
    ax.set_axisbelow(True)
    limpar(ax)
    titulo(ax, "O modelo recupera o que a regra deixa passar: arquivados e suspensos",
           "Revocação no conjunto de teste (1.273 processos): parte de cada classe real que foi reconhecida.")
    salvar(fig, "ted04_regra_modelo.png")


def fig_abstencao(r):
    total = r["teste"]["modelo"]["por_classe"]
    n = int(sum(total[c]["support"] for c in total))
    linhas = []
    for item in r["abstencao"]:
        if item["limiar"] not in (0, 0.8, 0.9):
            continue
        sugeridos = item["n"]
        certos = round(sugeridos * item["acuracia"])
        errados = sugeridos - certos
        leitura = n - sugeridos
        linhas.append({"limiar": item["limiar"], "certos": certos, "errados": errados, "leitura": leitura,
                       "por_mil": por_mil([certos, errados, leitura], n)})
    fig, ax = plt.subplots(figsize=(8, 3.0))
    nomes = {0: "sem limiar", 0.8: "confiança ≥ 0,8", 0.9: "confiança ≥ 0,9"}
    cores = [CINZA_CLARO, ALERTA, CINZA]
    for i, linha in enumerate(linhas):
        yi = len(linhas) - 1 - i
        esquerda = 0
        for valor, cor in zip(linha["por_mil"], cores):
            ax.barh(yi, valor, left=esquerda, color=cor, height=0.6, edgecolor="white", linewidth=2)
            esquerda += valor
        c, e, l = linha["por_mil"]
        ax.text(c / 2, yi, f"{c} certas", ha="center", va="center", color=ESCURO, fontsize=9)
        ax.text(1020, yi + 0.13, f"{e} erradas", ha="left", va="center", color=ALERTA,
                fontsize=9.5, fontweight="bold")
        ax.text(1020, yi - 0.17, f"{l} para leitura" if l else "nenhuma para leitura", ha="left",
                va="center", color=TINTA, fontsize=9)
    ax.set_yticks(range(len(linhas)), [nomes[l["limiar"]] for l in linhas][::-1])
    ax.set_xlim(0, 1000)
    ax.set_xticks([0, 250, 500, 750, 1000], ["0", "250", "500", "750", "1.000"])
    ax.set_ylim(-0.5, len(linhas) - 0.5)
    limpar(ax, manter=())
    titulo(ax, "Com confiança mínima de 0,8, os erros caem de 78 para 46 a cada mil",
           "Destino de cada 1.000 processos do teste: sugestão certa, sugestão errada ou leitura pelo advogado.")
    salvar(fig, "ted04_abstencao.png")
    return {"teste_n": n, "limiares": linhas}


def fig_generalizacao(r):
    g = r["generalizacao"]
    cenarios = [
        ("Teste reservado (SP e RJ, sorteio agrupado)", r["teste"]["modelo"]["f1_macro"], ESCURO),
        ("Treino SP → teste RJ*", g["treino SP -> teste RJ"]["f1_macro"], CINZA),
        ("Treino até 2017 → teste 2018-2019", g["treino ate 2017 -> teste 2018-2019"]["f1_macro"], CINZA),
        ("Treino até 2018 → teste 2019", g["treino ate 2018 -> teste 2019"]["f1_macro"], CINZA),
        ("Treino RJ → teste SP", g["treino RJ -> teste SP"]["f1_macro"], ALERTA),
    ]
    regra = r["teste"]["regra"]["f1_macro"]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    for i, (nome, valor, cor) in enumerate(cenarios):
        yi = len(cenarios) - 1 - i
        ax.barh(yi, valor, color=cor, height=0.6)
        if cor == ALERTA:
            ax.text(valor + 0.015, yi, num(valor), va="center", color=ALERTA, fontsize=10, fontweight="bold")
        else:
            ax.text(valor - 0.015, yi, num(valor), va="center", ha="right", color="white", fontsize=9)
    ax.axvline(regra, color=TINTA, linestyle=(0, (4, 3)), linewidth=1)
    ax.text(regra + 0.012, -0.5, f"regra de palavras-chave\nno teste: {num(regra)}", ha="left", va="bottom",
            color=TINTA, fontsize=8.5)
    ax.set_yticks(range(len(cenarios)), [c[0] for c in cenarios][::-1])
    ax.set_xlim(0, 1.0)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0], ["0", "0,25", "0,50", "0,75", "1"])
    ax.set_ylim(-0.6, len(cenarios) - 0.1)
    limpar(ax, manter=())
    titulo(ax, "Fora do vocabulário em que foi treinado, o modelo perde a utilidade",
           "F1 macro por cenário de treino e teste. *RJ não tem suspensos; F1 sobre duas classes.")
    salvar(fig, "ted04_generalizacao.png")


def main():
    r = json.loads((RESULTADOS / "ted03_resultados.json").read_text(encoding="utf-8"))
    fig_janela(r)
    fig_regra_modelo(r)
    numeros = {"abstencao": fig_abstencao(r)}
    fig_generalizacao(r)
    (RESULTADOS / "ted04_numeros.json").write_text(json.dumps(numeros, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
    print(json.dumps(numeros, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
