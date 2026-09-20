"""
Prepara a versao PUBLICAVEL do dataset e gera o cartao de descricao.

A versao de trabalho e a versao publicavel sao arquivos diferentes, de proposito:

  trabalho   texto integral, numero CNJ, nome da unidade, evidencias
  publicavel sem texto, identificadores pseudonimizados, so o tabulado

Motivo: as sentencas trazem nome das partes e, no caso de insalubridade,
descricao de condicao de saude apurada em pericia. Republicar isso em lote e
coisa diferente de a decisao estar consultavel uma a uma no portal do tribunal.

    python exportar_dataset.py
    python exportar_dataset.py --manter-unidade
    python exportar_dataset.py --tudo       # inclui as classes de escape

Le o arquivo unico (../data/juripredict.csv) e publica, por padrao, apenas a
populacao do modelo. Com --tudo, publica tambem as linhas de escape, que levam
`populacao` e `motivo_fora` e nao tem y.
"""

import argparse
import hashlib
import os
from datetime import date

import numpy as np
import pandas as pd

# colunas que nunca vao para a versao publicavel
REMOVER = ["caso_id", "doc_id", "arquivo_bruto", "sha256", "evidencia",
           "trecho", "texto", "motivo_exclusao", "entra_no_modelo",
           # identificam o documento de origem, nao o caso
           "classe", "tipo_documento", "estrategia_corte", "coletado_em"]

# Uma regiao com menos unidades que isto nao esconde nada: publicada ao lado
# da unidade pseudonimizada, revela qual vara e.
PISO_UNIDADES_POR_REGIAO = 2

SAL_PADRAO = "juripredict"


def pseudonimizar(serie, prefixo, sal):
    """Mapeia valores para rotulos estaveis: unidade_01, unidade_02, ..."""
    unicos = sorted(x for x in serie.dropna().unique())
    ordem = sorted(unicos, key=lambda v: hashlib.sha256((sal + str(v)).encode()).hexdigest())
    mapa = {v: f"{prefixo}_{i+1:02d}" for i, v in enumerate(ordem)}
    return serie.map(mapa), mapa


def exportar(entrada, saida, manter_unidade, sal, tudo=False):
    df = pd.read_csv(entrada, parse_dates=["data_sentenca"])
    original = len(df), len(df.columns)

    # A versao publicavel e a do MODELO. As linhas de escape existem no arquivo
    # de trabalho para auditoria; publicar tudo junto, sem o leitor perceber a
    # coluna `populacao`, produziria taxa-base errada em qualquer groupby.
    if "populacao" in df.columns and not tudo:
        df = df[df["populacao"] == "modelo"].copy()
        # Depois do filtro `populacao` vale 'modelo' em toda linha e
        # `motivo_fora` fica vazia. Publicar coluna constante convida a
        # trata-la como variavel; publicar coluna toda nula e so ruido.
        df = df.drop(columns=[c for c in ("populacao", "motivo_fora")
                              if c in df.columns])

    pub = df.drop(columns=[c for c in REMOVER if c in df.columns]).copy()

    # identificador do processo -> hash truncado, estavel e nao reversivel
    if "numero_cnj" in pub.columns:
        pub["id"] = pub["numero_cnj"].map(
            lambda v: hashlib.sha256((sal + str(v)).encode()).hexdigest()[:12])
        pub = pub.drop(columns=["numero_cnj"])

    mapa_unidade = {}
    if "vara" in pub.columns and not manter_unidade:
        pub["unidade"], mapa_unidade = pseudonimizar(pub["vara"], "unidade", sal)

        # `regiao` sai do MUNICIPIO da unidade. Onde uma regiao tem uma unidade
        # so, publicar as duas juntas desfaz a pseudonimizacao: quem souber como
        # a regiao foi derivada sabe qual vara e aquela. Eram 2 das 22 aqui.
        #
        # As singulares viram um balde unico, no mesmo espirito do invariante
        # I3 - abaixo do piso, suprime-se com o motivo em vez de exibir frágil.
        if "regiao" in pub.columns:
            por_regiao = pub.groupby("regiao")["vara"].nunique()
            solitarias = set(por_regiao[por_regiao < PISO_UNIDADES_POR_REGIAO].index)
            if solitarias:
                pub["regiao"] = pub["regiao"].where(
                    ~pub["regiao"].isin(solitarias), "demais")
                print(f"regiao: {len(solitarias)} categoria(s) com menos de "
                      f"{PISO_UNIDADES_POR_REGIAO} unidades agrupadas em 'demais' "
                      f"({', '.join(sorted(solitarias))})")

        pub = pub.drop(columns=["vara"])

    # data exata -> ano e trimestre: reduz reidentificacao sem perder o eixo
    if "data_sentenca" in pub.columns:
        pub["ano"] = pub["data_sentenca"].dt.year
        pub["trimestre"] = pub["data_sentenca"].dt.quarter
        pub = pub.drop(columns=["data_sentenca"])

    frente = [c for c in ("id", "unidade", "ano", "trimestre") if c in pub.columns]
    pub = pub[frente + [c for c in pub.columns if c not in frente]]

    os.makedirs(saida, exist_ok=True)
    caminho = os.path.join(saida, "juripredict_insalubridade.csv")
    pub.to_csv(caminho, index=False)

    cartao = gerar_cartao(pub, df, manter_unidade)
    with open(os.path.join(saida, "DATASET_CARD.md"), "w", encoding="utf-8") as f:
        f.write(cartao)

    if mapa_unidade:
        with open(os.path.join(saida, "_mapa_unidades_NAO_PUBLICAR.csv"), "w",
                  encoding="utf-8") as f:
            f.write("unidade_real,rotulo\n")
            for real, rot in mapa_unidade.items():
                f.write(f"{real},{rot}\n")

    print(f"entrada : {original[0]} linhas, {original[1]} colunas")
    print(f"saida   : {len(pub)} linhas, {len(pub.columns)} colunas")
    print(f"removidas: {sorted(set(df.columns) - set(pub.columns))}")
    print(f"\n{caminho}")
    print(f"{os.path.join(saida, 'DATASET_CARD.md')}")
    if mapa_unidade:
        print(f"{os.path.join(saida, '_mapa_unidades_NAO_PUBLICAR.csv')}  "
              f"<- mantenha fora do repositorio")


def gerar_cartao(pub, orig, manter_unidade):
    n = len(pub)
    taxa = pub["y"].mean() if "y" in pub.columns else float("nan")
    # dataset sem data_sentenca chega aqui com `ano` inteiro em NaN. Dizer isso
    # no cartao e melhor que estourar depois de o CSV ja ter sido gravado.
    tem_ano = "ano" in pub.columns and pub["ano"].notna().any()
    anos = f"{int(pub.ano.min())}–{int(pub.ano.max())}" if tem_ano else "—"
    n_unid = pub["unidade"].nunique() if "unidade" in pub.columns else (
        pub["vara"].nunique() if "vara" in pub.columns else 0)

    linhas_col = []
    for c in pub.columns:
        tipo = "numérica" if pd.api.types.is_numeric_dtype(pub[c]) else "categórica"
        falta = (pub[c].isna() | (pub[c].astype(str) == "nao_informado")).mean()
        distintos = pub[c].nunique()
        linhas_col.append(f"| `{c}` | {tipo} | {distintos} | {falta:.0%} |")

    return f"""# JuriPredict — Insalubridade / TRT-16

Conjunto de dados tabulares derivado de sentenças trabalhistas de primeiro grau
do Tribunal Regional do Trabalho da 16ª Região, com o resultado do pedido de
adicional de insalubridade rotulado.

**Versão:** 1.0 · **Gerado em:** {date.today().isoformat()} · **Linhas:** {n}

## O que este conjunto é

Uma linha por processo × pedido de adicional de insalubridade julgado no mérito
em primeiro grau. A variável-resposta `y` indica se o adicional foi deferido em
qualquer extensão.

- **Período:** {anos}
- **Unidades julgadoras:** {n_unid}
- **Taxa-base (y=1):** {taxa:.1%}

## O que este conjunto NÃO é

- **Não é** uma amostra de todos os processos ajuizados. A população é a dos
  pedidos que **chegaram a sentença de mérito**. Acordos homologados, extinções
  sem resolução do mérito e prescrição total do pedido ficam fora, por definição.
  Usar `y` como probabilidade de êxito ao ajuizar é erro de interpretação.
- **Não contém** texto das decisões, nome das partes, número do processo, nem
  qualquer identificador direto.
- **Não é** representativo da Justiça do Trabalho brasileira. O recorte é um
  tribunal regional.

## Colunas

| Coluna | Tipo | Valores distintos | Ausente |
|---|---|---|---|
{chr(10).join(linhas_col)}

## Procedência

Duas fontes públicas, unidas pelo número único do processo:

- metadados processuais da base nacional do Conselho Nacional de Justiça;
- inteiro teor das sentenças no repositório oficial de jurisprudência da Justiça
  do Trabalho.

O rótulo `y` é extraído do dispositivo da sentença por regra determinística, com
os casos ambíguos encaminhados a revisão. As variáveis de conteúdo são extraídas
da fundamentação por modelo de linguagem, sobre amostra.

## Privacidade

{"A unidade julgadora é identificada nominalmente." if manter_unidade else
"As unidades julgadoras estão pseudonimizadas em rótulos estáveis (`unidade_01`, `unidade_02`, …). O mapeamento não é publicado."}
O identificador `id` é hash truncado do número do processo: estável entre
versões, não reversível. A data foi reduzida a ano e trimestre.

Nenhuma coluna contém dado pessoal de parte, advogado ou magistrado.

## Limitações conhecidas

- **Cobertura da fonte.** Nem toda sentença proferida está indexada no
  repositório de jurisprudência. A taxa de cobertura por unidade e ano é medida
  à parte e deve ser consultada antes de comparar unidades.
- **Erro de rotulagem.** A extração automática é validada contra leitura humana
  em conjunto de referência, com concordância reportada **separadamente por
  classe de resultado**. Concordância global alta pode esconder erro que depende
  do desfecho.
- **Medição condicionada ao resultado.** Algumas variáveis de conteúdo só são
  mencionadas na sentença quando servem ao argumento vencedor. Essas estão
  marcadas e não devem ser usadas como preditoras sem validação pareada.
- **Seleção de disputas.** Casos que chegam a julgamento não são amostra
  aleatória dos ajuizados (Priest e Klein, 1984).
- **Deriva normativa.** O período pode atravessar mudanças de entendimento.
  Avaliação com divisão aleatória superestima o desempenho; use divisão temporal.

## Uso sugerido

Classificação binária com avaliação **temporal**, comparada a linhas de base de
taxa-base. Métrica primária de calibração (escore de Brier), não de acurácia.

## Citação

Sousa, E. C. *JuriPredict — Insalubridade / TRT-16*, v1.0, 2026.
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="../data/juripredict.csv")
    ap.add_argument("--saida", default="../../publicacao")
    ap.add_argument("--tudo", action="store_true",
                    help="publica tambem as classes de escape")
    ap.add_argument("--manter-unidade", action="store_true",
                    help="publica o nome real da unidade julgadora")
    ap.add_argument("--sal", default=SAL_PADRAO)
    a = ap.parse_args()
    exportar(a.entrada, a.saida, a.manter_unidade, a.sal, a.tudo)