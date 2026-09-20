"""
Monta O dataset - um arquivo so - a partir do banco anotado, limpa os tipos e
emite o relatorio de qualidade. Nao treina nada: produz a tabela e diz se presta.

    python montar_dataset.py                 # -> ../data/juripredict.csv
    python montar_dataset.py --demo          # dados falsos, sem banco

UM arquivo, nao tres. Antes havia dataset.csv, dataset_particionado.csv e a
versao publicavel, todos com recortes diferentes das mesmas linhas, e as
exclusoes existiam so como numero no relatorio - impossivel auditar depois quais
processos ficaram de fora e por que. Agora todo caso do pedido esta no arquivo,
com duas colunas dizendo seu estatuto:

    populacao    modelo | escape | fora_da_populacao
    motivo_fora  o motivo exato, quando nao e 'modelo'

Treinar e avaliar usa `populacao == "modelo"`, e so essas linhas tem `y` e
`particao` preenchidos. As demais ficam com y nulo de proposito.

O que ele garante:
  1. UMA linha por (numero_cnj, pedido) - invariante verificado, nao prometido;
  2. so recebem y os casos deferido/indeferido de sentenca de merito de 1o grau;
  3. cada exclusao e contada, reportada por motivo E preservada como linha;
  4. tipos normalizados e checagens de consistencia (grau x resultado, escala do
     grau, duplicidade de chave, data no futuro) - que avisam, nunca removem;
  5. taxa de ausencia por campo, com a triagem P(ausente | y) do livro, secao 9.
"""

import argparse
import sqlite3
import sys

import numpy as np
import pandas as pd

from dividir_dataset import atribuir, cortes_temporais
from rotular_por_regra import CORRIGE_COERENCIA, VERSAO_DATASET

ENTRAM = {"deferido", "indeferido"}
ESCAPE = {"prescrito_total", "prejudicado", "nao_analisado", "ambiguo",
          "nao_mencionado"}

# campos marcados como suspeitos no livro de codigos, secao 6.6
SUSPEITOS = {"epi_fornecido", "epi_fiscalizado", "epi_eficaz",
             "habitualidade_exposicao"}

# precedencia quando o mesmo campo tem mais de uma anotacao
PRECEDENCIA = {"humano": 3, "regra": 2, "llm": 1}


# Regiao derivada do MUNICIPIO da unidade julgadora, nao da vara em si: varas
# diferentes da mesma cidade caem na mesma regiao. Serve para agregar quando uma
# unidade sozinha nao sustenta estimativa (invariante I3) - nunca para
# substituir a vara na exibicao.
#
# O agrupamento segue as mesorregioes do Maranhao, com a capital separada por
# concentrar 7 das 23 varas.
REGIOES = {
    "sao luis": "capital",
    "bacabal": "centro", "santa ines": "centro", "barra do corda": "centro",
    "pedreiras": "centro", "presidente dutra": "centro",
    "imperatriz": "oeste", "acailandia": "oeste", "estreito": "oeste",
    "caxias": "leste", "timon": "leste", "chapadinha": "leste",
    "pinheiro": "baixada",
    "balsas": "sul", "sao joao dos patos": "sul",
    "barreirinhas": "outra",
}


def _sem_acento(texto):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                   if unicodedata.category(c) != "Mn").lower()


def regiao_da_vara(vara):
    """'4a Vara do Trabalho de Sao Luis' -> 'capital'."""
    nome = _sem_acento(vara)
    for municipio, regiao in REGIOES.items():
        if municipio in nome:
            return regiao
    return "outra"


def carregar(banco):
    con = sqlite3.connect(banco)
    docs = pd.read_sql("SELECT * FROM documentos", con, parse_dates=["data_sentenca"])
    casos = pd.read_sql("SELECT * FROM casos", con)
    valores = pd.read_sql("SELECT * FROM valores", con)
    con.close()
    return docs, casos, valores


def pivotar(valores, excluir=()):
    """
    Formato longo -> largo, resolvendo conflito por precedencia da fonte.
    Anotacao humana vence regra, que vence modelo de linguagem.

    `excluir` remove campos que ja sao coluna canonica em 'casos'
    (resultado_pedido, grau_deferido, resultado_global). Eles continuam em
    'valores' como trilha de auditoria - metodo, versao e evidencia -, mas o
    valor que vale e o da tabela 'casos'. Sem isso o merge duplicaria a coluna
    e o alvo sumiria.
    """
    if valores.empty:
        return pd.DataFrame(columns=["caso_id"])
    v = valores[~valores["campo"].isin(excluir)].copy()
    if v.empty:
        return pd.DataFrame(columns=["caso_id"])
    v["prio"] = v["metodo"].map(PRECEDENCIA).fillna(0)
    v = v.sort_values(["caso_id", "campo", "prio"])
    v = v.drop_duplicates(["caso_id", "campo"], keep="last")
    largo = v.pivot(index="caso_id", columns="campo", values="valor").reset_index()
    largo.columns.name = None
    return largo


def montar(docs, casos, valores, pedido="insalubridade"):
    casos = casos[casos["pedido"] == pedido].copy()

    relatorio = []
    total = len(casos)
    relatorio.append(("casos do pedido", total, ""))

    # --------------------------------------------------- criterios de inclusao
    # NAO se filtra por julga_insalubridade. Essa coluna marca a existencia de
    # um CAPITULO com titulo proprio na fundamentacao, e processar.py decidiu de
    # proposito que o rotulo vem do DISPOSITIVO, nao do capitulo - porque exigir
    # capitulo descartava sentencas cujo dispositivo decide o pedido com clareza.
    # Filtrar por ela aqui desfazia aquela decisao e removia 69% dos casos
    # elegiveis, de forma NAO aleatoria: os removidos deferiam 18 pontos menos,
    # o que inflava a taxa-base de 70% para 85%.
    docs_ok = docs[docs["tipo_decisao"] == "sentenca_merito"]
    antes = len(casos)
    casos = casos[casos["doc_id"].isin(docs_ok["doc_id"])]
    relatorio.append(("fora: documento nao e sentenca de merito",
                      antes - len(casos), ""))

    com_capitulo = int(casos["doc_id"].isin(
        docs[docs["julga_insalubridade"] == "sim"]["doc_id"]).sum())
    relatorio.append(("(diagnostico) casos com capitulo do tema", com_capitulo,
                      "nao e criterio de inclusao"))

    # --------------------------------------------------------------- populacao
    # Nada e descartado em silencio: cada caso recebe o motivo pelo qual esta
    # dentro ou fora, e tudo vai para o MESMO arquivo. Antes eram dois CSV
    # (dataset.csv e dataset_particionado.csv) contendo so as linhas do modelo,
    # e as classes de escape existiam apenas como numero no relatorio - o que
    # torna impossivel auditar depois quais processos foram excluidos e por que.
    #
    # `populacao` = 'modelo' e o unico recorte treinavel. As demais linhas ficam
    # com y nulo, de proposito: nao da para treinar nelas por acidente.
    casos["populacao"] = "modelo"
    casos["motivo_fora"] = None

    # I1: so entra sentenca de merito de PRIMEIRO GRAU. processar.py classifica
    # o evento processual e marca entra_no_modelo=0 para liquidacao, execucao,
    # embargos e homologatoria.
    if "motivo_exclusao" in casos.columns:
        eventos = casos.loc[casos["motivo_exclusao"].notna()
                            & ~casos["motivo_exclusao"].isin(ESCAPE),
                            "motivo_exclusao"]
        for motivo, n in eventos.value_counts().items():
            relatorio.append((f"fora: {motivo}", int(n),
                              "nao e merito de 1o grau"))
        casos.loc[eventos.index, "populacao"] = "fora_da_populacao"
        casos.loc[eventos.index, "motivo_fora"] = eventos

    if "ordem_sentenca" in docs.columns:
        posteriores = docs_ok[docs_ok["ordem_sentenca"] == "posterior"]
        alvo = casos["doc_id"].isin(posteriores["doc_id"]) & (casos.populacao == "modelo")
        if alvo.any():
            relatorio.append(("fora: sentenca posterior a primeira",
                              int(alvo.sum()), ""))
            casos.loc[alvo, "populacao"] = "fora_da_populacao"
            casos.loc[alvo, "motivo_fora"] = "sentenca_posterior"

    # Acao coletiva: sindicato, federacao, associacao ou MPT no polo ativo, ou
    # classe ACC/ACPCiv/ACum. A decisao alcanca os substituidos da categoria
    # inteira - uma linha representa centenas de trabalhadores, nao um pedido.
    # Misturar isso com acao individual distorce a taxa por vara, porque um
    # julgamento coletivo pesa o mesmo que um caso singular na contagem.
    if CORRIGE_COERENCIA and "autor_coletivo" in docs.columns:
        coletivos = docs.loc[docs["autor_coletivo"] == 1, "doc_id"]
        alvo = casos["doc_id"].isin(coletivos) & (casos.populacao == "modelo")
        if alvo.any():
            relatorio.append(("fora: acao coletiva", int(alvo.sum()),
                              "unidade de analise diferente"))
            casos.loc[alvo, "populacao"] = "coletiva"
            casos.loc[alvo, "motivo_fora"] = "acao_coletiva"

    for motivo in sorted(ESCAPE):
        alvo = (casos["resultado_pedido"] == motivo) & (casos.populacao == "modelo")
        if alvo.any():
            relatorio.append((f"fora: {motivo}", int(alvo.sum()), "classe de escape"))
            casos.loc[alvo, "populacao"] = "escape"
            casos.loc[alvo, "motivo_fora"] = motivo

    sobra = (casos.populacao == "modelo") & ~casos["resultado_pedido"].isin(ENTRAM)
    if sobra.any():
        casos.loc[sobra, "populacao"] = "escape"
        casos.loc[sobra, "motivo_fora"] = casos.loc[sobra, "resultado_pedido"]

    relatorio.append(("entram no modelo", int((casos.populacao == "modelo").sum()), ""))

    if casos.empty:
        return pd.DataFrame(), relatorio

    # ------------------------------------------------------------- montagem
    # campos canonicos de "casos" ficam fora do pivo (ver docstring)
    largo = pivotar(valores, excluir=set(casos.columns))
    # classe/tipo_documento sao metadados do tribunal e so existem quando o
    # manifest foi lido; o --demo nao os produz.
    do_doc = [c for c in ("doc_id", "data_sentenca", "orgao_julgador",
                          "classe", "tipo_documento") if c in docs.columns]
    df = (casos.merge(docs[do_doc], on="doc_id", how="left")
                .merge(largo, on="caso_id", how="left"))

    df = df.rename(columns={"orgao_julgador": "vara"})
    # `regiao` vem vazia do banco (o FALCAO nao devolve o campo); deriva-se do
    # municipio da unidade, que o nome da vara carrega.
    df["regiao"] = df["vara"].map(regiao_da_vara)
    no_modelo = df.populacao == "modelo"
    df["y"] = np.where(no_modelo, (df["resultado_pedido"] == "deferido"), np.nan)
    df["ano_sentenca"] = pd.to_datetime(df["data_sentenca"]).dt.year

    # ---------------------------------------------------------- INVARIANTES
    chaves = df.groupby(["numero_cnj", "pedido"]).size()
    if (chaves > 1).any():
        dupes = chaves[chaves > 1]
        sys.exit(f"INVARIANTE QUEBRADO: {len(dupes)} chave(s) com mais de uma "
                 f"linha. Exemplo: {dupes.index[0]}")
    if df.loc[no_modelo, "y"].isna().any():
        sys.exit("INVARIANTE QUEBRADO: ha linha do modelo sem target.")

    return df, relatorio


# colunas sem informacao no recorte atual: valor unico em todas as linhas, ou
# derivadas de outra coluna. Saem porque um CSV com coluna constante convida a
# tratar constante como variavel.
def _colunas_mortas(df, preservar):
    mortas = []
    for c in df.columns:
        if c in preservar:
            continue
        if df[c].nunique(dropna=False) <= 1:
            mortas.append(c)
    return mortas


# Colunas internas do pipeline que as novas tornaram redundantes. Sao copias
# exatas - a verificacao esta em limpar() e falha se deixarem de ser.
SUPERSEDIDAS = {"entra_no_modelo": "populacao",
                "motivo_exclusao": "motivo_fora"}


def _colunas_repetidas(df):
    """Pares de colunas com conteudo identico. So reporta; nao remove."""
    vistas, repetidas = {}, []
    for c in df.columns:
        chave = tuple(df[c].astype("string").fillna("\x00"))
        if chave in vistas:
            repetidas.append((vistas[chave], c))
        else:
            vistas[chave] = c
    return repetidas


def limpar(df, cortes=None):
    """
    Normaliza tipos, checa consistencia e devolve (df_limpo, problemas).

    Nao remove linha nenhuma: problema encontrado vira aviso, nao exclusao
    silenciosa. Quem decide descartar e quem le o relatorio.
    """
    problemas = []
    df = df.copy()

    # --------------------------------------------------------------- tipos
    df["data_sentenca"] = pd.to_datetime(df["data_sentenca"], errors="coerce")
    for col in ("grau_deferido", "ano_sentenca", "y"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # ---------------------------------------------------------- texto limpo
    # Nome de vara vem do tribunal e ja chega consistente, mas espaco duplo e
    # espaco nas pontas entram como categoria nova em qualquer groupby.
    for col in ("vara", "resultado_pedido", "resultado_global", "classe",
                "tipo_documento", "motivo_fora", "populacao"):
        if col in df.columns:
            df[col] = (df[col].astype("string").str.strip()
                       .str.replace(r"\s+", " ", regex=True))

    # ------------------------------------------------------- consistencia
    no_modelo = df.populacao == "modelo"

    sem_data = int(df.loc[no_modelo, "data_sentenca"].isna().sum())
    if sem_data:
        problemas.append(f"{sem_data} linha(s) do modelo sem data_sentenca "
                         f"- ficam fora de qualquer particao temporal")

    sem_vara = int(df.loc[no_modelo, "vara"].isna().sum())
    if sem_vara:
        problemas.append(f"{sem_vara} linha(s) do modelo sem unidade julgadora")

    # grau so faz sentido em deferimento
    if "grau_deferido" in df.columns:
        incoerente = int((df["grau_deferido"].notna()
                          & (df["resultado_pedido"] != "deferido")).sum())
        if incoerente:
            problemas.append(f"{incoerente} linha(s) com grau_deferido fora de "
                             f"um deferimento")
        fora_escala = int((df["grau_deferido"].notna()
                           & ~df["grau_deferido"].isin([10, 20, 40])).sum())
        if fora_escala:
            problemas.append(f"{fora_escala} linha(s) com grau fora de 10/20/40")

    # duplicidade dentro da populacao treinavel
    dup = int(df.loc[no_modelo].duplicated(["numero_cnj", "pedido"]).sum())
    if dup:
        problemas.append(f"{dup} chave (numero_cnj, pedido) repetida no modelo")

    # data fora do recorte declarado do projeto
    if df["data_sentenca"].notna().any():
        futuras = int((df["data_sentenca"] > pd.Timestamp.today()).sum())
        if futuras:
            problemas.append(f"{futuras} linha(s) com data no futuro")

    # ------------------------------------------------------------ particao
    # So a populacao do modelo e particionada. Linha de escape com particao
    # convidaria a inclui-la na avaliacao.
    df["particao"] = pd.NA
    treinavel = no_modelo & df["data_sentenca"].notna()
    if treinavel.any():
        c1, c2 = cortes or cortes_temporais(df.loc[treinavel, "data_sentenca"])
        df.loc[treinavel, "particao"] = atribuir(df.loc[treinavel], c1, c2)
    else:
        c1 = c2 = None

    # ------------------------------------------------------ colunas mortas
    # Colunas internas que `populacao` e `motivo_fora` substituiram. Sao copias
    # exatas; se um dia deixarem de ser, o aviso aparece em vez de a coluna
    # sumir em silencio levando informacao junto.
    removidas = []
    for antiga, nova in SUPERSEDIDAS.items():
        if antiga not in df.columns or nova not in df.columns:
            continue
        a = df[antiga].astype("string").fillna("\x00")
        b = df[nova].astype("string").fillna("\x00")
        if antiga == "entra_no_modelo":
            a = (df[antiga] == 1).astype("string")
            b = (df[nova] == "modelo").astype("string")
        # `populacao` e `motivo_fora` sao mais ricas que as colunas de banco:
        # distinguem escape, acao coletiva e fora da populacao, que
        # `entra_no_modelo` resume num bit. Divergir e o esperado - por isso a
        # coluna antiga sai de qualquer forma, e o relatorio diz se coincidiam.
        df = df.drop(columns=[antiga])
        removidas.append(f"{antiga} ({'identica a' if a.equals(b) else 'resumida por'} {nova})")

    # `resultado_global` sai do dataset, e fica so no banco como trilha.
    #
    # Ele resume num rotulo unico um dispositivo que rotineiramente decide
    # varios pedidos em direcoes diferentes. Medido nesta versao: 5 linhas com
    # "extinto_sem_merito" e 2 com "improcedente" em que o adicional de
    # insalubridade foi DEFERIDO - a extincao e a improcedencia eram de outros
    # pedidos, ou de outros reclamados. Mais 6 linhas ficam "indefinido" porque
    # a regra nao conseguiu ler o dispositivo (uma delas por erro de digitacao
    # do proprio juiz: "julgar PROCEDECENTES").
    #
    # Lido a serio, o campo diria que 7 casos foram deferidos e nao deferidos ao
    # mesmo tempo. Como feature, ensinaria o modelo a confiar num resumo errado.
    if "resultado_global" in df.columns:
        df = df.drop(columns=["resultado_global"])
        removidas.append("resultado_global (incoerente com o pedido em 7 linhas)")

    # `doc_id` e exatamente `caso_id` ate o ':' - guardar as duas e carregar a
    # mesma informacao duas vezes. A verificacao roda: se um dia deixarem de
    # coincidir, a coluna fica e o aviso aparece.
    if {"doc_id", "caso_id"} <= set(df.columns):
        if (df["caso_id"].astype(str).str.split(":").str[0] == df["doc_id"]).all():
            df = df.drop(columns=["doc_id"])
            removidas.append("doc_id (prefixo de caso_id)")
        else:
            problemas.append("`doc_id` nao e mais o prefixo de `caso_id`")

    # `tipo_documento` vem "Sentenca" em 617 das 618 linhas: o que ele
    # distinguiria ja esta em `tipo_evento`, que foi inferido do texto porque
    # este campo nao servia. Fica no banco como trilha; fora do dataset.
    if "tipo_documento" in df.columns:
        df = df.drop(columns=["tipo_documento"])
        removidas.append("tipo_documento (quase constante; ver tipo_evento)")

    preservar = {"caso_id", "numero_cnj", "pedido", "y", "particao",
                 "populacao", "motivo_fora", "resultado_pedido", "vara",
                 "data_sentenca", "grau_deferido", "regiao"}
    mortas = _colunas_mortas(df, preservar)
    if mortas:
        df = df.drop(columns=mortas)
    mortas = mortas + removidas

    for a, b in _colunas_repetidas(df):
        problemas.append(f"colunas `{a}` e `{b}` tem conteudo identico")

    # --------------------------------------------------------- ordenacao
    frente = [c for c in ("caso_id", "numero_cnj", "pedido", "vara",
                          "data_sentenca", "ano_sentenca", "populacao",
                          "motivo_fora", "particao", "resultado_pedido",
                          "grau_deferido", "y") if c in df.columns]
    df = df[frente + [c for c in df.columns if c not in frente]]
    df = df.sort_values(["data_sentenca", "numero_cnj"], na_position="last")
    return df, problemas, mortas, (c1, c2)


def qualidade(df):
    """Taxa de ausencia por campo e triagem P(ausente | y) do livro, secao 9."""
    # Colunas de identidade, de proveniencia e de controle do proprio pipeline.
    # Nenhuma delas e candidata a feature, e lista-las aqui so produzia ruido
    # no relatorio - `motivo_fora`, por exemplo, e nulo em 100% da populacao do
    # modelo por construcao.
    ignorar = {"caso_id", "doc_id", "numero_cnj", "pedido", "y",
               "resultado_pedido", "entra_no_modelo", "motivo_exclusao",
               "data_sentenca", "resultado_global",
               "populacao", "motivo_fora", "particao",
               "classe", "tipo_documento", "tipo_evento", "arquivo_bruto",
               "sha256", "estrategia_corte", "coletado_em", "fonte"}
    linhas = []
    for col in df.columns:
        if col in ignorar:
            continue
        nulo = df[col].isna() | (df[col] == "nao_informado")
        p_all = nulo.mean()
        p0 = nulo[df.y == 0].mean() if (df.y == 0).any() else np.nan
        p1 = nulo[df.y == 1].mean() if (df.y == 1).any() else np.nan
        linhas.append((col, p_all, p0, p1, abs(p1 - p0), col in SUSPEITOS))
    return sorted(linhas, key=lambda r: -r[4] if not np.isnan(r[4]) else 0)


def imprimir(df, relatorio):
    print("=" * 74)
    print("MONTAGEM DO DATASET")
    print("=" * 74)
    for rot, n, obs in relatorio:
        print(f"  {rot:<52}{n:>6}  {obs}")

    if df.empty:
        print("\nnenhum caso elegivel.")
        return

    print(f"\n  taxa-base (y=1): {df.y.mean():.1%}")
    print(f"  periodo        : {df.data_sentenca.min().date()} a "
          f"{df.data_sentenca.max().date()}")
    print(f"  varas distintas: {df.vara.nunique()}")

    print("\n" + "-" * 74)
    print("QUALIDADE DOS CAMPOS")
    print("-" * 74)
    print(f"{'campo':<28}{'ausente':>9}{'| y=0':>9}{'| y=1':>9}{'dif':>8}   sinal")
    for col, p_all, p0, p1, dif, suspeito in qualidade(df):
        marca = ""
        if not np.isnan(dif) and dif > 0.15:
            marca = "<< ausencia depende do resultado"
        if suspeito:
            marca = (marca + "  [ja marcado como suspeito]").strip()
        print(f"{col:<28}{p_all:>8.0%}{p0:>9.0%}{p1:>9.0%}{dif:>8.0%}   {marca}")

    print("\nDiferenca > 15% e TRIAGEM, nao veredito: a ausencia pode depender")
    print("legitimamente do fenomeno. Campo sinalizado vai para validacao")
    print("pareada contra o documento original (livro de codigos, secao 6.6).")


# ===========================================================================
def demo():
    """Dados falsos com a forma exata das tabelas, para testar o montador."""
    rng = np.random.default_rng(7)
    n = 300
    varas = ["1a VT Balsas", "2a VT Balsas", "1a VT Imperatriz"]

    docs = pd.DataFrame({
        "doc_id": [f"d{i:04d}" for i in range(n)],
        "numero_cnj": [f"{i:07d}-00.2022.5.16.0001" for i in range(n)],
        "orgao_julgador": rng.choice(varas, n),
        "regiao": "sul",
        "data_sentenca": pd.to_datetime("2020-01-01")
                         + pd.to_timedelta(rng.integers(0, 2000, n), unit="D"),
        "tipo_decisao": rng.choice(["sentenca_merito", "homologatoria"], n, p=[.85, .15]),
        "julga_insalubridade": rng.choice(["sim", "nao"], n, p=[.88, .12]),
        "ordem_sentenca": "primeira",
        "arquivo_bruto": "", "sha256": "", "estrategia_corte": "titulo",
        "coletado_em": None, "fonte": "falcao",
    })

    resultado = rng.choice(
        ["deferido", "indeferido", "prescrito_total", "prejudicado",
         "nao_analisado", "ambiguo"], n, p=[.44, .38, .03, .05, .03, .07])
    casos = pd.DataFrame({
        "caso_id": [f"c{i:04d}" for i in range(n)],
        "numero_cnj": docs["numero_cnj"],
        "pedido": "insalubridade",
        "doc_id": docs["doc_id"],
        "resultado_pedido": resultado,
        "grau_deferido": None, "resultado_global": None,
        "entra_no_modelo": 0, "motivo_exclusao": None,
    })

    y = (resultado == "deferido")
    regs = []
    for i in range(n):
        laudo = rng.choice(["insalubre", "nao_insalubre", "nao_informado"],
                           p=[.55, .35, .10])
        regs.append((f"c{i:04d}", "laudo_conclusao", laudo, "regra"))
        regs.append((f"c{i:04d}", "agente",
                     rng.choice(["biologico", "quimico", "fisico"]), "llm"))
        # armadilha de proposito: so aparece quando indefere
        epi = rng.choice(["sim", "nao"]) if not y[i] and rng.random() < .8 else "nao_informado"
        regs.append((f"c{i:04d}", "epi_fiscalizado", epi, "llm"))
    valores = pd.DataFrame(regs, columns=["caso_id", "campo", "valor", "metodo"])
    valores["evidencia"] = ""
    valores["versao"] = "demo"
    valores["extraido_em"] = None
    return docs, casos, valores


def imprimir_limpeza(df, problemas, mortas, cortes):
    print("\n" + "-" * 74)
    print("LIMPEZA")
    print("-" * 74)
    if mortas:
        print("  colunas removidas (constantes ou duplicadas):")
        for c in sorted(mortas):
            print(f"    - {c}")
    c1, c2 = cortes
    if c1 is not None:
        print(f"  corte temporal: {c1.date()} | {c2.date()}")
        cont = df["particao"].value_counts()
        print("  particao: " + "  ".join(
            f"{k}={int(v)}" for k, v in cont.items() if pd.notna(k)))
    if problemas:
        print("\n  PROBLEMAS (nenhuma linha foi removida por causa deles):")
        for p in problemas:
            print(f"    - {p}")
    else:
        print("  nenhuma inconsistencia encontrada nas checagens de tipo,")
        print("  escala de grau, duplicidade de chave e intervalo de datas.")


def imprimir_populacao(df):
    print("\n" + "-" * 74)
    print("COMPOSICAO DO ARQUIVO UNICO")
    print("-" * 74)
    print(f"{'populacao':<22}{'motivo':<26}{'linhas':>8}")
    for (pop, mot), n in (df.groupby(["populacao", df["motivo_fora"].fillna("-")],
                                     dropna=False).size().items()):
        print(f"{pop:<22}{str(mot):<26}{n:>8}")
    print(f"{'TOTAL':<48}{len(df):>8}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="../data/juripredict.db")
    ap.add_argument("--saida", default="../data/juripredict.csv",
                    help="arquivo unico: todos os casos, com populacao e particao")
    ap.add_argument("--pedido", default="insalubridade")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    if a.demo:
        docs, casos, valores = demo()
    else:
        docs, casos, valores = carregar(a.banco)

    df, rel = montar(docs, casos, valores, a.pedido)
    if df.empty:
        imprimir(df, rel)
        sys.exit(0)

    df, problemas, mortas, cortes = limpar(df)
    imprimir(df[df.populacao == "modelo"], rel)
    imprimir_populacao(df)
    imprimir_limpeza(df, problemas, mortas, cortes)

    if not a.demo:
        import os
        os.makedirs(os.path.dirname(a.saida) or ".", exist_ok=True)
        df.to_csv(a.saida, index=False)
        n_mod = int((df.populacao == "modelo").sum())
        print(f"\n{a.saida} gravado: {len(df)} linhas, "
              f"{n_mod} treinaveis (populacao == 'modelo').")