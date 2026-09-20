"""
Auditoria de cobertura do Falcao (DEC-001).

Testa se estar indexado no Falcao e independente do resultado do processo.
O resultado vem dos movimentos do DataJud, que existem tanto para os processos
cobertos quanto para os nao cobertos - por isso o teste e possivel.

    # etapa 1: sorteia a amostra e ja grava o resultado de cada processo
    python auditoria_cobertura.py amostrar --n 40 --de 2024 --ate 2026

    # etapa 1b: preenche 'no_corpus_local' cruzando com o manifesto do coletor
    python auditoria_cobertura.py cruzar

    # voce preenche 'encontrado_no_falcao' a mao consultando o portal

    # etapa 2: analisa
    python auditoria_cobertura.py analisar
"""

import argparse
import csv
import json
import os
import random
import re
import sys
from math import comb, sqrt

PISO_CELULA = 0.70   # abaixo disso a celula nao sustenta taxa-base publicavel

ENDPOINT = "https://api-publica.datajud.cnj.jus.br/api_publica_trt16/_search"

# Classificacao do desfecho pelo NOME do movimento (mais robusto que o codigo,
# que pode variar entre versoes da TPU). Ordem importa.
PADROES_DESFECHO = [
    ("acordo", r"homologa[çc][ãa]o\s+de\s+(acordo|transa[çc][ãa]o)|concilia[çc][ãa]o"),
    ("extinto_sem_merito", r"sem\s+resolu[çc][ãa]o\s+do\s+m[ée]rito"),
    ("parcial", r"proced[êe]ncia\s+em\s+parte|parcialmente\s+procedente"),
    ("improcedente", r"improced[êe]ncia"),
    ("procedente", r"proced[êe]ncia"),
]


# ---------------------------------------------------------------------------
# Etapa 1 - amostragem
# ---------------------------------------------------------------------------

def classificar_movimentos(movimentos):
    nomes = " | ".join((m.get("nome") or "") for m in movimentos).lower()
    for rotulo, padrao in PADROES_DESFECHO:
        if re.search(padrao, nomes):
            return rotulo
    return "indefinido"


def buscar_frame(assunto, de, ate, teto):
    """Baixa o frame do DataJud com paginacao search_after."""
    import requests

    from extrair_llm import carregar_env
    from coletar_datajud import ASSUNTO_INSALUBRIDADE, FILTRO_PRIMEIRO_GRAU
    carregar_env()

    chave = os.environ.get("DATAJUD_API_KEY", "").strip()
    if not chave:
        sys.exit("DATAJUD_API_KEY vazia. Coloque no .env da raiz do projeto.")

    headers = {"Authorization": f"APIKey {chave}", "Content-Type": "application/json"}
    processos, ultimo = [], None

    while len(processos) < teto:
        corpo = {
            "size": 100,
            "sort": [{"@timestamp": {"order": "asc"}}],
            # grau.keyword, nao grau: medido contra a API, `{"term":
            # {"grau": "G1"}}` devolve zero porque o campo e analisado.
            # Sem este filtro entram 90.086 recursos de segundo grau.
            "query": {"bool": {"filter": [
                FILTRO_PRIMEIRO_GRAU,
                {"term": {"assuntos.codigo": assunto}},
                {"range": {"dataAjuizamento": {
                    "gte": f"{de}-01-01", "lte": f"{ate}-12-31"}}},
            ]}},
        }
        if ultimo:
            corpo["search_after"] = ultimo

        r = requests.post(ENDPOINT, headers=headers, json=corpo, timeout=60)
        r.raise_for_status()
        hits = r.json()["hits"]["hits"]
        if not hits:
            break
        processos.extend(h["_source"] for h in hits)
        ultimo = hits[-1]["sort"]
        print(f"  {len(processos)} processos no frame...")

    return processos


def amostrar(n, assunto, de, ate, teto, saida, semente):
    processos = buscar_frame(assunto, de, ate, teto)
    print(f"\nframe: {len(processos)} processos")

    # so entram processos ja julgados - o desfecho precisa existir
    julgados = []
    for p in processos:
        desfecho = classificar_movimentos(p.get("movimentos", []))
        if desfecho != "indefinido":
            julgados.append((p, desfecho))
    print(f"com desfecho identificavel: {len(julgados)}")

    if len(julgados) < n:
        sys.exit(f"frame menor que a amostra pedida ({len(julgados)} < {n})")

    # ALEATORIO. Pegar os N primeiros seria amostra enviesada por data.
    random.seed(semente)
    amostra = random.sample(julgados, n)

    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["numero_cnj", "ano", "orgao_julgador", "desfecho_datajud",
                    "no_corpus_local", "encontrado_no_falcao", "observacao"])
        from coletar_datajud import mascarar_cnj
        for p, desfecho in amostra:
            w.writerow([
                mascarar_cnj(p.get("numeroProcesso")),
                (p.get("dataAjuizamento") or "")[:4],
                (p.get("orgaoJulgador") or {}).get("nome"),
                desfecho,
                "",          # <- `cruzar` preenche a partir do manifesto
                "",          # <- voce preenche consultando o portal
                "",
            ])

    print(f"\n{saida} gravado com {n} linhas (semente={semente}).")
    print("Preencha 'encontrado_no_falcao' com sim/nao e rode 'analisar'.")


# ---------------------------------------------------------------------------
# Etapa 2 - analise
# ---------------------------------------------------------------------------

def censo(arquivo):
    """
    Cobertura por celula (vara, ano), calculada na populacao inteira.
    Responde a objecao de heterogeneidade sem custo de amostragem.

    CSV de entrada: vara,ano,n_datajud,n_falcao
    """
    linhas = list(csv.DictReader(open(arquivo, encoding="utf-8")))
    celulas = []
    for l in linhas:
        dj, fa = int(l["n_datajud"]), int(l["n_falcao"])
        if dj == 0:
            continue
        celulas.append((l["vara"], l["ano"], dj, fa, min(fa / dj, 1.0)))

    if not celulas:
        sys.exit("nenhuma celula com denominador > 0.")

    tot_dj = sum(c[2] for c in celulas)
    tot_fa = sum(min(c[3], c[2]) for c in celulas)
    global_ = tot_fa / tot_dj

    print("=" * 66)
    print(f"COBERTURA GLOBAL: {global_:.0%}  ({tot_fa} de {tot_dj})")
    print("=" * 66)

    celulas.sort(key=lambda c: c[4])
    print(f"\n{'vara':<28}{'ano':>6}{'datajud':>9}{'falcao':>8}{'cob':>7}")
    for vara, ano, dj, fa, cob in celulas:
        marca = "  <<" if cob < PISO_CELULA else ""
        print(f"{vara[:27]:<28}{ano:>6}{dj:>9}{fa:>8}{cob:>6.0%}{marca}")

    piores = [c for c in celulas if c[4] < PISO_CELULA]
    amplitude = celulas[-1][4] - celulas[0][4]

    print("\n" + "-" * 66)
    print("VEREDITO")
    print("-" * 66)
    print(f"  amplitude entre celulas: {amplitude:.0%} "
          f"(de {celulas[0][4]:.0%} a {celulas[-1][4]:.0%})")

    if piores or amplitude > 0.30:
        print("\n  COBERTURA HETEROGENEA. A media global esconde o problema.")
        print(f"  {len(piores)} celula(s) abaixo do piso de {PISO_CELULA:.0%}.")
        print("  Nao publique taxa-base para essas celulas: ou restrinja o")
        print("  produto as celulas bem cobertas, ou troque de fonte.")
    else:
        print("\n  Cobertura razoavelmente homogenea entre celulas.")
        print("  Ainda assim, reporte a cobertura junto de cada taxa-base.")

    print("\n  Lembrete: numerador e denominador precisam usar a MESMA data")
    print("  (data da sentenca), e o Falcao conta documentos enquanto o")
    print("  DataJud conta processos - deduplique antes de comparar.")


def wilson(sucessos, total, z=1.96):
    """IC de Wilson: correto para proporcoes com n pequeno."""
    if total == 0:
        return (0.0, 0.0)
    p = sucessos / total
    d = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / d
    margem = z * sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / d
    return (max(0.0, centro - margem), min(1.0, centro + margem))


def fisher_bilateral(a, b, c, d):
    """Teste exato de Fisher, sem dependencia externa."""
    n = a + b + c + d
    linha1, col1 = a + b, a + c

    def prob(x):
        return (comb(linha1, x) * comb(n - linha1, col1 - x)) / comb(n, col1)

    observada = prob(a)
    limites = range(max(0, col1 - (n - linha1)), min(linha1, col1) + 1)
    return sum(prob(x) for x in limites if prob(x) <= observada * (1 + 1e-9))


def analisar(arquivo):
    linhas = list(csv.DictReader(open(arquivo, encoding="utf-8")))
    preenchidas = [l for l in linhas
                   if (l["encontrado_no_falcao"] or "").strip().lower() in ("sim", "nao", "não")]

    if len(preenchidas) < len(linhas):
        print(f"AVISO: {len(linhas) - len(preenchidas)} linhas sem preenchimento; ignoradas.\n")
    if not preenchidas:
        sys.exit("nenhuma linha preenchida.")

    achou = lambda l: (l["encontrado_no_falcao"] or "").strip().lower() == "sim"
    favoravel = lambda l: l["desfecho_datajud"] in ("procedente", "parcial")

    n = len(preenchidas)
    encontrados = [l for l in preenchidas if achou(l)]
    faltantes = [l for l in preenchidas if not achou(l)]

    cob = len(encontrados) / n
    lo, hi = wilson(len(encontrados), n)
    print("=" * 62)
    print(f"COBERTURA: {cob:.0%}  (IC95% {lo:.0%} a {hi:.0%}, n={n})")
    print("=" * 62)

    a = sum(1 for l in encontrados if favoravel(l))
    b = len(encontrados) - a
    c = sum(1 for l in faltantes if favoravel(l))
    d = len(faltantes) - c

    print("\n                  favoravel   desfavoravel")
    print(f"  no Falcao         {a:>6}       {b:>6}")
    print(f"  fora do Falcao    {c:>6}       {d:>6}")

    if len(encontrados) and len(faltantes):
        p_in, p_out = a / len(encontrados), c / len(faltantes)
        p_valor = fisher_bilateral(a, b, c, d)
        print(f"\n  taxa favoravel dentro : {p_in:.0%}")
        print(f"  taxa favoravel fora   : {p_out:.0%}")
        print(f"  diferenca             : {abs(p_in - p_out):.0%}")
        print(f"  Fisher bilateral      : p = {p_valor:.3f}")
    else:
        p_valor = None
        print("\n  um dos grupos esta vazio: teste de dependencia impossivel.")

    print("\n" + "-" * 62)
    print("VEREDITO")
    print("-" * 62)

    if hi < 0.50:
        print("  COBERTURA BAIXA. Decisivo mesmo com n pequeno: o Falcao nao")
        print("  serve como frame amostral. Acione o plano de troca de fonte.")
    elif lo < 0.70:
        print("  COBERTURA INCERTA. Amplie a amostra para ~150 antes de decidir.")
    else:
        print("  COBERTURA ACEITAVEL para seguir.")

    if p_valor is None:
        pass
    elif p_valor < 0.05:
        # Fisher e EXATO: um positivo vale em qualquer n. O que n pequeno
        # compromete e a capacidade de detectar, nao a validade do que detectou.
        print(f"\n  SELECAO DEPENDENTE DO RESULTADO (p = {p_valor:.3f}).")
        print("  Valido mesmo neste n - Fisher e exato, e detectar com poucos")
        print("  casos significa que o efeito e grande.")
        print("  Sua taxa-base sairia enviesada. Troque de fonte ou reposicione.")
    elif n < 120:
        print(f"\n  INCONCLUSIVO quanto a dependencia: n={n} tem pouco poder.")
        print("  Nao houve deteccao, mas isso nao e evidencia de ausencia.")
        print("  Se a cobertura passou, amplie para ~150 e rode de novo.")
    else:
        print(f"\n  Sem evidencia de dependencia do resultado (p = {p_valor:.3f}, n={n}).")
        print("  Registre o n junto do resultado.")


# ---------------------------------------------------------------------------

def _autoteste():
    """Casos sinteticos para conferir a estatistica antes de usar de verdade."""
    print("wilson(20,40) =", tuple(round(x, 3) for x in wilson(20, 40)))
    assert 0.34 < wilson(20, 40)[0] < 0.36
    assert 0.64 < wilson(20, 40)[1] < 0.66

    # tabela sem associacao nenhuma
    p = fisher_bilateral(10, 10, 10, 10)
    print("fisher(10,10,10,10) = %.3f  (esperado ~1.0)" % p)
    assert p > 0.9

    # associacao forte
    p = fisher_bilateral(18, 2, 2, 18)
    print("fisher(18,2,2,18)   = %.6f (esperado << 0.05)" % p)
    assert p < 0.001

    # caso classico com resposta conhecida: tabela do cha de Fisher
    p = fisher_bilateral(3, 1, 1, 3)
    print("fisher(3,1,1,3)     = %.4f (esperado ~0.4857)" % p)
    assert abs(p - 0.4857) < 0.002

    print("\nOK: estatistica conferida.")


# ---------------------------------------------------------------------------
# Etapa 1b - cruzamento automatico com o corpus ja coletado
# ---------------------------------------------------------------------------

def cruzar(arquivo, manifesto):
    """
    Preenche `no_corpus_local` comparando com o manifesto do coletor.

    ATENCAO - isto NAO substitui a coluna `encontrado_no_falcao`, e a diferenca
    entre as duas nao e detalhe:

        no_corpus_local       o processo esta na coleta que ja foi feita
        encontrado_no_falcao  o processo esta indexado no portal

    A coleta tem limites proprios - o texto da busca, o numero de paginas, a
    janela de datas. Um processo pode estar no Falcao e fora do nosso corpus.
    Tratar as duas colunas como a mesma coisa transforma "nao coletamos" em
    "o tribunal nao publicou", que e a conclusao oposta.

    Serve para medir a cobertura DO DATASET, que e o que o invariante I3 exige
    exibir ao lado de cada taxa.
    """
    import os
    import sqlite3
    if not os.path.exists(manifesto):
        sys.exit(f"manifesto nao encontrado: {manifesto}")

    con = sqlite3.connect(manifesto)
    coletados = {re.sub(r"\D", "", n or "")
                 for (n,) in con.execute("SELECT numero_cnj FROM documentos")}
    con.close()
    coletados.discard("")

    linhas = list(csv.DictReader(open(arquivo, encoding="utf-8")))
    if not linhas:
        sys.exit("planilha vazia.")

    n_sim = 0
    for l in linhas:
        digitos = re.sub(r"\D", "", l.get("numero_cnj") or "")
        achou = digitos in coletados
        l["no_corpus_local"] = "sim" if achou else "nao"
        n_sim += achou

    with open(arquivo, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)

    print(f"{len(linhas)} processos conferidos contra {len(coletados)} coletados")
    print(f"  no corpus local : {n_sim:>4}  ({n_sim/len(linhas):.0%})")
    print(f"  fora            : {len(linhas)-n_sim:>4}")
    print("\nIsto e a cobertura do DATASET, nao a do portal. Para saber se o")
    print("processo esta no Falcao e nao foi coletado, preencha")
    print("`encontrado_no_falcao` a mao e rode `analisar`.")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("amostrar")
    a.add_argument("--n", type=int, default=40)
    a.add_argument("--assunto", type=int, default=13875,
                   help="codigo TPU; 13875 = Adicional de Insalubridade")
    a.add_argument("--de", type=int, default=2024)
    a.add_argument("--ate", type=int, default=2026)
    a.add_argument("--teto", type=int, default=5000, help="tamanho maximo do frame")
    a.add_argument("--saida", default="../data/auditoria.csv")
    a.add_argument("--semente", type=int, default=42)

    b = sub.add_parser("analisar")
    b.add_argument("--arquivo", default="../data/auditoria.csv")

    d = sub.add_parser("cruzar")
    d.add_argument("--arquivo", default="../data/auditoria.csv")
    d.add_argument("--manifesto", default="../data/manifests/falcao.sqlite")

    c = sub.add_parser("censo")
    c.add_argument("--arquivo", default="../data/censo.csv",
                   help="CSV: vara,ano,n_datajud,n_falcao")

    sub.add_parser("autoteste")

    args = p.parse_args()
    if args.cmd == "amostrar":
        amostrar(args.n, args.assunto, args.de, args.ate, args.teto, args.saida, args.semente)
    elif args.cmd == "analisar":
        analisar(args.arquivo)
    elif args.cmd == "cruzar":
        cruzar(args.arquivo, args.manifesto)
    elif args.cmd == "censo":
        censo(args.arquivo)
    else:
        _autoteste()
