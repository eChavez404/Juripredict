"""
Gold set: amostragem, anotacao manual e medicao de concordancia.

E aqui que a verdade entra no dataset. Sem esta etapa voce nao sabe se os
rotulos valem alguma coisa - e um rotulo errado nao aparece em metrica nenhuma,
porque o modelo aprende o erro com perfeicao.

    python gold_set.py amostrar --n 50            # sorteia e gera a planilha
    # voce le as sentencas e preenche a planilha a mao
    python gold_set.py comparar --arquivo gold_set.csv

A regra decisoria do livro de codigos, secao 9: concordancia global alta NAO
basta. Se a concordancia difere entre deferidos e indeferidos, o erro de medicao
depende do resultado - que e o modo de falha que o projeto tenta evitar.
"""

import argparse
import csv
import os
import random
import sqlite3
import sys
from collections import defaultdict
from math import sqrt

CAMPOS = ["resultado_pedido", "grau_deferido", "pericia_realizada",
          "laudo_conclusao", "laudo_grau", "agente"]


# ---------------------------------------------------------------- amostragem
def mecanismo(metodo, evidencia):
    """
    COMO o rotulo foi produzido. E este o eixo em que o erro varia.

    Estratificar so pelo resultado (deferido/indeferido) faz a amostra ser
    dominada pelos casos faceis - aqueles em que a regra leu o verbo decisorio
    direto do dispositivo, que sao a maioria. Os rotulos duvidosos estao nos
    inferidos e nos lidos por modelo, e sobre esses a amostra nao diria nada.
    """
    ev = evidencia or ""
    if metodo == "llm":
        return "llm_leitura"
    if ev.startswith("inferido: procedencia parcial"):
        return "regra_inferida_fundamentacao"
    if ev.startswith("inferido"):
        return "regra_inferida_global"
    if ev.startswith("tema citado apenas"):
        return "regra_so_reflexo"
    return "regra_direta"


def amostrar(banco, n, saida, semente):
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    linhas = con.execute("""
        SELECT c.caso_id, c.numero_cnj, c.resultado_pedido, c.entra_no_modelo,
               d.orgao_julgador, d.data_sentenca, d.arquivo_bruto,
               v.metodo, v.evidencia
        FROM casos c
        JOIN documentos d ON d.doc_id = c.doc_id
        LEFT JOIN valores v ON v.caso_id = c.caso_id
             AND v.campo = 'resultado_pedido'
             AND v.metodo = (SELECT metodo FROM valores v2
                             WHERE v2.caso_id = c.caso_id
                               AND v2.campo = 'resultado_pedido'
                             ORDER BY CASE v2.metodo WHEN 'humano' THEN 0
                                      WHEN 'llm' THEN 1 ELSE 2 END LIMIT 1)
    """).fetchall()
    con.close()

    if not linhas:
        sys.exit("nenhum caso no banco. rode processar.py antes.")

    # Estrato = mecanismo x resultado. Duas perguntas diferentes, e a amostra
    # precisa responder as duas:
    #   - o rotulo esta certo? (varia por mecanismo)
    #   - o erro depende do desfecho? (varia por resultado)
    # Os casos EXCLUIDOS tambem entram: se 81 processos foram descartados como
    # "nao mencionado" por engano, isso nao aparece em metrica nenhuma.
    # Grupos grossos de proposito. Com 60 casos, 18 estratos dao 3 casos cada e
    # nao medem nada - o intervalo de confianca de uma proporcao com n=3 cobre
    # quase todo o eixo. Seis estratos dao ~10 cada, que ja distingue 90% de 60%.
    GRUPO = {"regra_direta": "regra_direta",
             "regra_inferida_global": "regra_inferida",
             "regra_inferida_fundamentacao": "regra_inferida",
             "regra_so_reflexo": "regra_inferida",
             "llm_leitura": "llm_leitura"}
    por_classe = defaultdict(list)
    for l in linhas:
        mec = GRUPO[mecanismo(l["metodo"], l["evidencia"])]
        if l["entra_no_modelo"]:
            chave = f"{mec} | {l['resultado_pedido']}"
        else:
            # os excluidos entram como um bloco so: a pergunta ali nao e
            # "deferido ou indeferido", e "esta exclusao estava certa?"
            chave = "EXCLUIDO (verificar se a exclusao procede)"
        por_classe[chave].append(l)

    random.seed(semente)
    amostra, restante = [], n
    classes = sorted(por_classe, key=lambda c: len(por_classe[c]))
    for i, classe in enumerate(classes):
        cota = restante // (len(classes) - i)
        pega = min(cota, len(por_classe[classe]))
        amostra += random.sample(por_classe[classe], pega)
        restante -= pega
    random.shuffle(amostra)

    os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)
    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["caso_id", "numero_cnj", "orgao_julgador", "data_sentenca",
                    "arquivo"] + CAMPOS + ["evidencia", "observacao"])
        for l in amostra:
            w.writerow([l["caso_id"], l["numero_cnj"], l["orgao_julgador"],
                        l["data_sentenca"], l["arquivo_bruto"]]
                       + [""] * len(CAMPOS) + ["", ""])

    print(f"{len(amostra)} casos em {saida}")
    print("\ndistribuicao por estrato (mecanismo do rotulo x resultado):")
    print(f"  {'estrato':<48}{'amostra':>8}{'universo':>10}")
    for classe in sorted(por_classe, key=lambda c: -len(por_classe[c])):
        chaves = {a["caso_id"] for a in amostra}
        na = sum(1 for x in por_classe[classe] if x["caso_id"] in chaves)
        print(f"  {classe:<48}{na:>8}{len(por_classe[classe]):>10}")
    print("\nAbra cada arquivo, leia, e preencha as colunas seguindo o livro de")
    print("codigos. NAO olhe o rotulo automatico antes de anotar - a planilha")
    print("nao traz o rotulo justamente por isso.")


# ---------------------------------------------------------------- comparacao
def kappa(a, b):
    """Kappa de Cohen: concordancia corrigida pelo acaso."""
    pares = [(x, y) for x, y in zip(a, b) if x and y]
    if not pares:
        return float("nan")
    n = len(pares)
    po = sum(1 for x, y in pares if x == y) / n
    cats = set(x for x, _ in pares) | set(y for _, y in pares)
    pe = sum((sum(1 for x, _ in pares if x == c) / n) *
             (sum(1 for _, y in pares if y == c) / n) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2*n)) / d
    m = z * sqrt(p*(1-p)/n + z**2/(4*n**2)) / d
    return (max(0, c-m), min(1, c+m))


def comparar(banco, arquivo):
    gold = list(csv.DictReader(open(arquivo, encoding="utf-8")))
    gold = [g for g in gold if (g.get("resultado_pedido") or "").strip()]
    if not gold:
        sys.exit("planilha sem linhas preenchidas.")

    con = sqlite3.connect(banco)
    auto = defaultdict(dict)
    for caso_id, campo, valor, metodo in con.execute(
            "SELECT caso_id, campo, valor, metodo FROM valores"):
        auto[caso_id][(campo, metodo)] = valor
    con.close()

    print("=" * 72)
    print(f"CONCORDANCIA CONTRA LEITURA HUMANA  (n = {len(gold)})")
    print("=" * 72)
    print(f"{'campo':<20}{'metodo':<8}{'n':>5}{'geral':>9}{'IC95':>16}"
          f"{'| defer.':>10}{'| indef.':>10}{'kappa':>8}")

    alertas = []
    for campo in CAMPOS:
        for metodo in ("regra", "llm", "humano"):
            g, a, classes = [], [], []
            for linha in gold:
                vg = (linha.get(campo) or "").strip()
                va = auto.get(linha["caso_id"], {}).get((campo, metodo))
                if not vg or va is None:
                    continue
                g.append(vg); a.append(va)
                classes.append((linha.get("resultado_pedido") or "").strip())
            if len(g) < 5:
                continue

            acertos = sum(1 for x, y in zip(g, a) if x == y)
            lo, hi = wilson(acertos, len(g))

            def por(classe):
                par = [(x, y) for x, y, c in zip(g, a, classes) if c == classe]
                if not par:
                    return float("nan")
                return sum(1 for x, y in par if x == y) / len(par)

            pd_, pi = por("deferido"), por("indeferido")
            k = kappa(g, a)
            print(f"{campo:<20}{metodo:<8}{len(g):>5}{acertos/len(g):>8.0%}"
                  f"   [{lo:>4.0%},{hi:>4.0%}]{pd_:>10.0%}{pi:>10.0%}{k:>8.2f}")

            if pd_ == pd_ and pi == pi and abs(pd_ - pi) > 0.10:
                alertas.append((campo, metodo, abs(pd_ - pi)))

    print("\n" + "-" * 72)
    if alertas:
        print("ALERTA: concordancia depende do resultado")
        for campo, metodo, dif in alertas:
            print(f"  {campo} ({metodo}): {dif:.0%} de diferenca entre as classes")
        print("\n  Erro de medicao correlacionado ao desfecho contamina o modelo")
        print("  sem aparecer em nenhuma metrica. Corrija a extracao ou exclua")
        print("  o campo antes de treinar.")
    else:
        print("Sem diferenca relevante de concordancia entre as classes.")
        print("Com este n, isso significa 'sem sinal grosseiro', nao 'validado'.")

    print("\nCriterio para seguir: o erro precisa ser menor que a diferenca que")
    print("se pretende mostrar entre unidades julgadoras.")


# ---------------------------------------------------------------- demo
def demo(banco, saida):
    """Preenche a planilha simulando um anotador que erra mais nos indeferidos."""
    import random
    random.seed(11)
    con = sqlite3.connect(banco)
    casos = con.execute("SELECT caso_id, resultado_pedido FROM casos").fetchall()
    con.close()
    escolhidos = random.sample(casos, min(30, len(casos)))
    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["caso_id", "numero_cnj", "orgao_julgador", "data_sentenca",
                    "arquivo"] + CAMPOS + ["evidencia", "observacao"])
        for caso_id, res in escolhidos:
            errar = random.random() < (0.25 if res == "indeferido" else 0.03)
            humano = ("deferido" if res == "indeferido" else "indeferido") if errar else res
            w.writerow([caso_id, "", "", "", ""] + [humano] + [""]*(len(CAMPOS)-1) + ["", ""])
    print(f"planilha simulada em {saida} ({len(escolhidos)} linhas)\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    s1 = sub.add_parser("amostrar")
    s1.add_argument("--banco", default="../data/juripredict.db")
    s1.add_argument("--n", type=int, default=50)
    s1.add_argument("--saida", default="../data/gold_set.csv")
    s1.add_argument("--semente", type=int, default=42)

    s2 = sub.add_parser("comparar")
    s2.add_argument("--banco", default="../data/juripredict.db")
    s2.add_argument("--arquivo", default="../data/gold_set.csv")

    s3 = sub.add_parser("demo")
    s3.add_argument("--banco", default="../data/juripredict.db")
    s3.add_argument("--saida", default="../data/gold_demo.csv")

    a = ap.parse_args()
    if a.cmd == "amostrar":
        amostrar(a.banco, a.n, a.saida, a.semente)
    elif a.cmd == "comparar":
        comparar(a.banco, a.arquivo)
    else:
        demo(a.banco, a.saida)