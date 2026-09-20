"""
Gera os pares texto -> rotulo, em JSONL, para ajustar um modelo de linguagem
pequeno na tarefa de EXTRACAO.

    python gerar_finetune.py                         # destilacao (padrao)
    python gerar_finetune.py --fonte gold            # so anotacao humana
    python gerar_finetune.py --demo                  # banco falso, sem dado real

O alvo NAO e prever o resultado do pedido - isso e trabalho do modelo tabular, e
ali fine-tuning nao se aplica. O alvo e substituir a chamada de API do
extrair_llm.py por um modelo local que leia a fundamentacao e devolva os campos
estruturados, comecando pelo resultado do pedido.

Tres decisoes, porque as falhas correspondentes nao aparecem em metrica:

  1. TREINAR por destilacao, MEDIR contra humano. O treino usa o rotulo da
     regra onde ela decide e o da anotacao por modelo onde ela recusou - imitar
     o professor e o objetivo, ja que o modelo local existe para substitui-lo.
     O gold set fica reservado para a avaliacao: a particao de TESTE so e
     gerada quando ele existe, porque um teste rotulado pelo mesmo processo que
     gerou o treino mede o proprio ajuste.

  2. Caso 'ambiguo' fica de fora. E a regra dizendo que nao sabe; ensinar isso
     ao aluno so transfere a incerteza.

  3. A particao e HERDADA do dataset (../data/juripredict.csv), nao recalculada
     - senao um caso poderia estar no treino de um e no teste do outro, e a
     avaliacao do modelo pequeno contra o dataset perderia sentido.

O texto vai para o JSONL como esta na sentenca. Identificador e mascarado, mas
isso NAO e anonimizacao: a fundamentacao de insalubridade descreve condicao de
saude apurada em pericia. O JSONL fica em finetune/, que nao e versionado, e
nao deve sair da maquina.
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

from dividir_dataset import atribuir, cortes_temporais
from extrair_llm import SCHEMAS, VERSAO_PROMPT
from rotular_por_regra import TEMAS as TEMAS_REGEX

VERSAO_FINETUNE = "finetune-v1"

# O alvo primario da extracao: o resultado do pedido. Nao esta em SCHEMAS
# porque o extrair_llm.py so cuida das variaveis de conteudo - mas e este o
# campo que a regra produz, que eu anotei nos ambiguos, e que o modelo pequeno
# precisa aprender a devolver para substituir as duas coisas.
CAMPOS_RESULTADO = {
    "resultado_pedido": "deferido | indeferido | nao_analisado | nao_mencionado",
    "grau_deferido": "10 | 20 | 40 | null",
}


# dispositivo longo e truncado PELO FIM, onde a decisao esta
MAX_CHARS = 4000


def esquema_alvo(tema):
    return {**CAMPOS_RESULTADO, **SCHEMAS[tema]}

ARQUIVOS = {"treino": "treino.jsonl",
            "calibracao": "validacao.jsonl",
            "teste": "teste.jsonl"}

SISTEMA = (
    "Voce le trechos de uma sentenca trabalhista e extrai APENAS o que esta "
    "escrito neles. Nao infira, nao complete, nao suponha. Se a informacao nao "
    "aparece no texto, use null.\n\n"
    "Sobre o resultado do pedido:\n"
    "- \"deferido\" ou \"indeferido\" exigem decisao sobre o pedido de adicional "
    "de insalubridade em si;\n"
    "- \"nao_mencionado\" quando o adicional so aparece de passagem: como base "
    "de calculo, como verba ja paga em contracheque, em citacao de precedente "
    "ou norma, ou como exemplo em texto padrao;\n"
    "- \"nao_analisado\" quando houve desistencia, inepcia, litispendencia ou "
    "extincao sem resolucao do merito quanto a esse pedido.\n\n"
    "Sobre variaveis de conteudo, quando pedidas: anote a conclusao do PERITO, "
    "nao a do juiz. Se o perito concluiu pela insalubridade e o juiz indeferiu "
    "por outra razao, laudo_conclusao continua sendo \"insalubre\".\n\n"
    "Responda SOMENTE com um objeto JSON com exatamente estas chaves:\n{schema}"
)

# identificadores diretos; mascarar isso reduz reidentificacao, nao anonimiza
MASCARAS = [
    (r"\b\d{7}-?\d{2}\.?\d{4}\.?5\.?\d{2}\.?\d{4}\b", "[CNJ]"),
    (r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b", "[CPF]"),
    (r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b", "[CNPJ]"),
    (r"\bOAB[/\s]?[A-Z]{2}\s?n?[.º]?\s?\d+\b", "[OAB]"),
]


def redigir(texto):
    import re
    for padrao, marca in MASCARAS:
        texto = re.sub(padrao, marca, texto or "", flags=re.IGNORECASE)
    return texto


# ------------------------------------------------------------------ leitura
def carregar_capitulos(con, tema, com_recorte=True, fonte="dispositivo"):
    """
    Texto de entrada por caso, mais a data da sentenca - eixo do corte temporal.

    Fonte preferida: o capitulo recortado da fundamentacao. Mas ele so existe
    quando o titulo foi reconhecido (176 casos de 618 neste corpus), e exigi-lo
    descartaria 70% dos exemplos - a mesma armadilha que o montar_dataset.py ja
    caiu uma vez. Com `com_recorte`, os demais entram com os trechos em volta
    das mencoes ao tema, que e exatamente o material que sustentou a anotacao.
    """
    con.row_factory = sqlite3.Row
    linhas = con.execute("""
        SELECT c.caso_id, cap.texto AS capitulo, d.data_sentenca,
               d.orgao_julgador, d.arquivo_bruto
        FROM casos c
        JOIN documentos d ON d.doc_id = c.doc_id
        LEFT JOIN capitulos cap ON cap.caso_id = c.caso_id AND cap.tema = ?
        WHERE c.pedido = ?
    """, (tema, tema)).fetchall()

    from rotular_ambiguos import _trechos_do_tema
    from cortar_secoes import cortar
    import re
    padrao = re.compile(TEMAS_REGEX[tema], re.IGNORECASE)

    saida, contagem = [], defaultdict(int)
    for l in linhas:
        # Fonte "dispositivo": e de la que o rotulo da regra foi extraido, entao
        # e o texto coerente com o alvo. Alimentar a fundamentacao junto ensina
        # o modelo a usar sinais que o rotulo nao reflete.
        if fonte == "dispositivo":
            tem_arquivo = l["arquivo_bruto"] and Path(l["arquivo_bruto"]).exists()
            if not tem_arquivo:
                # sem o bruto em disco nao da para recortar o dispositivo; o
                # capitulo ja recortado serve, e a mistura fica no manifesto
                # em vez de o caso sumir em silencio
                alternativo = (l["capitulo"] or "").strip()
                if not alternativo:
                    contagem["sem_texto"] += 1
                    continue
                saida.append({"caso_id": l["caso_id"], "texto": alternativo,
                              "data_sentenca": l["data_sentenca"],
                              "fonte_texto": "capitulo"})
                contagem["capitulo"] += 1
                continue

            s = cortar(Path(l["arquivo_bruto"]).read_text(encoding="utf-8",
                                                          errors="replace"))
            disp = (s.dispositivo or "").strip()
            if len(disp) < 40:
                contagem["sem_dispositivo"] += 1
                continue
            if len(disp) > MAX_CHARS:
                disp = disp[-MAX_CHARS:]     # a decisao fica no fim
            saida.append({"caso_id": l["caso_id"], "texto": disp,
                          "data_sentenca": l["data_sentenca"],
                          "fonte_texto": "dispositivo"})
            contagem["dispositivo"] += 1
            continue

        texto = (l["capitulo"] or "").strip()
        marca = "capitulo"
        if texto:
            contagem["capitulo"] += 1
        elif com_recorte and l["arquivo_bruto"] and Path(l["arquivo_bruto"]).exists():
            s = cortar(Path(l["arquivo_bruto"]).read_text(encoding="utf-8",
                                                          errors="replace"))
            partes = (_trechos_do_tema(s.fundamentacao, padrao, maximo=3)
                      + _trechos_do_tema(s.dispositivo, padrao, maximo=2))
            texto, marca = "\n\n".join(p for p in partes if p).strip(), "recorte"
            if texto:
                contagem["recorte"] += 1
        if not texto:
            continue
        saida.append({"caso_id": l["caso_id"], "texto": texto,
                      "data_sentenca": l["data_sentenca"], "fonte_texto": marca})
    return saida, dict(contagem)


def rotulos_do_gold(con, caminho_csv):
    """
    Tabela gold_set primeiro; CSV do gold_set.py como alternativa.

    O gold_set.py de hoje grava a planilha em CSV e nao popula a tabela. As
    duas fontes valem, mas a origem entra no manifesto - saber de onde veio o
    rotulo e parte do invariante de proveniencia.
    """
    try:
        linhas = con.execute(
            "SELECT caso_id, campo, valor FROM gold_set "
            "WHERE valor IS NOT NULL AND TRIM(valor) <> ''").fetchall()
    except sqlite3.OperationalError:
        linhas = []

    if linhas:
        por_caso = defaultdict(dict)
        for l in linhas:
            por_caso[l["caso_id"]][l["campo"]] = l["valor"]
        return dict(por_caso), "tabela gold_set"

    if not caminho_csv or not Path(caminho_csv).exists():
        return {}, "nenhuma"

    # SO os campos de anotacao. A planilha tambem traz numero_cnj, vara, data e
    # caminho do arquivo, e aceitar qualquer coluna preenchida fazia uma
    # planilha AINDA EM BRANCO parecer um gold set completo - o que liberava a
    # particao de teste com rotulo de regra, justamente o que a trava impede.
    from gold_set import CAMPOS
    anotaveis = set(CAMPOS)

    por_caso = defaultdict(dict)
    with open(caminho_csv, encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            cid = (linha.get("caso_id") or "").strip()
            if not cid:
                continue
            for campo, valor in linha.items():
                valor = (valor or "").strip()
                if campo in anotaveis and valor:
                    por_caso[cid][campo] = valor
    por_caso = {k: v for k, v in por_caso.items() if v}
    if not por_caso:
        return {}, f"planilha {caminho_csv} ainda em branco"
    return dict(por_caso), f"planilha {caminho_csv}"


def rotulos_da_regra(con):
    linhas = con.execute(
        "SELECT caso_id, campo, valor FROM valores "
        "WHERE metodo = 'regra' AND valor IS NOT NULL").fetchall()
    por_caso = defaultdict(dict)
    for l in linhas:
        por_caso[l["caso_id"]][l["campo"]] = l["valor"]
    return dict(por_caso), "tabela valores (metodo=regra)"


def rotulos_por_destilacao(con):
    """
    Destilacao: o modelo pequeno aprende a imitar o professor que hoje roda no
    pipeline. O alvo de treino e o rotulo de LLM onde ele existe, e o da regra
    onde nao existe - a regra e determinista e de alta precisao nos casos em
    que o dispositivo nomeia o pedido; o LLM cobre justamente os que ela
    recusou. Cobrir so um dos dois ensinaria metade da tarefa.

    O gold set NAO entra aqui. Ele fica reservado para medir o aluno depois -
    treinar e avaliar na mesma anotacao mede o proprio ajuste.
    """
    por_caso, origem = defaultdict(dict), {}
    for metodo in ("regra", "llm"):          # llm sobrescreve regra
        for l in con.execute(
                "SELECT caso_id, campo, valor FROM valores "
                "WHERE metodo = ? AND valor IS NOT NULL", (metodo,)):
            por_caso[l["caso_id"]][l["campo"]] = l["valor"]
            origem[l["caso_id"]] = metodo
    n_llm = sum(1 for m in origem.values() if m == "llm")
    return (dict(por_caso), origem,
            f"destilacao: {n_llm} casos com rotulo de LLM, "
            f"{len(origem) - n_llm} com rotulo de regra")


# ------------------------------------------------------------------ montagem
def montar_pares(capitulos, rotulos, tema, redacao, alvo_simples=True):
    """
    Um par por caso que tem texto E rotulo. Os campos do alvo sao os do schema
    de extracao que a fonte de rotulo cobre - o resto vira null e e reportado.

    `alvo_simples` produz a resposta como um rotulo unico ("deferido"), que e o
    que classificador e LoRA local consomem. Sem ele, a resposta e o objeto JSON
    com todos os campos cobertos - mais informativo, e o formato que o
    extrair_llm.py devolve hoje.

    Nos dois casos o exemplo so entra se o resultado for deferido ou indeferido:
    treinar 'nao_mencionado' junto misturaria duas tarefas diferentes - decidir
    o pedido e reconhecer que nao houve pedido.
    """
    schema = esquema_alvo(tema)
    cobertos = sorted({c for r in rotulos.values() for c in r} & set(schema),
                      key=lambda c: list(schema).index(c))
    if not cobertos:
        return [], [], sorted(schema)

    sistema = SISTEMA.format(
        schema=json.dumps({c: schema[c] for c in cobertos},
                          ensure_ascii=False, indent=2))

    pares = []
    for cap in capitulos:
        anotacao = rotulos.get(cap["caso_id"])
        if not anotacao:
            continue
        alvo = {c: anotacao.get(c) for c in cobertos}
        if all(v in (None, "", "nao_informado") for v in alvo.values()):
            continue
        rotulo = alvo.get("resultado_pedido")
        # 'ambiguo' e a regra dizendo que nao sabe. Ensinar isso ao aluno so
        # transfere a incerteza; o caso fica de fora ate ter anotacao.
        if rotulo == "ambiguo":
            continue
        if alvo_simples and rotulo not in ("deferido", "indeferido"):
            continue

        texto = cap["texto"].strip()
        entrada = redigir(texto) if redacao else texto
        if alvo_simples:
            sis = ("Voce e um assistente juridico especializado em direito do "
                   "trabalho. Leia o trecho da sentenca e responda apenas com o "
                   "resultado do pedido de adicional de insalubridade.")
            usuario = f"{INSTRUCAO_SIMPLES}\n\n---\n{entrada}\n---"
            resposta = rotulo
        else:
            sis, usuario = sistema, entrada
            resposta = json.dumps(alvo, ensure_ascii=False)

        pares.append({
            "caso_id": cap["caso_id"],
            "data_sentenca": cap["data_sentenca"],
            "fonte_texto": cap.get("fonte_texto", "capitulo"),
            "rotulo": rotulo,
            "texto": entrada,          # sem instrucao nem delimitador
            "particao": None,
            "registro": {"messages": [
                {"role": "system", "content": sis},
                {"role": "user", "content": usuario},
                {"role": "assistant", "content": resposta},
            ]},
        })
    return pares, cobertos, sorted(set(schema) - set(cobertos))


def particionar(pares, dataset=None):
    """
    Usa a MESMA particao do dataset, nao um corte proprio.

    Um corte calculado aqui cairia em data diferente - os pares de fine-tuning
    incluem casos que o dataset deixa de fora -, e entao um caso poderia estar
    no treino de um e no teste do outro. Avaliar o modelo pequeno contra o
    dataset ficaria sem sentido.

    O corte proprio so entra quando o dataset ainda nao existe.
    """
    df = pd.DataFrame([{"caso_id": p["caso_id"],
                        "data_sentenca": p["data_sentenca"]} for p in pares])

    herdada = {}
    if dataset and Path(dataset).exists():
        d = pd.read_csv(dataset, usecols=lambda c: c in ("caso_id", "particao",
                                                         "data_sentenca"))
        herdada = dict(zip(d["caso_id"], d["particao"]))
        datas = pd.to_datetime(d.loc[d["particao"].notna(), "data_sentenca"])
        corte1, corte2 = cortes_temporais(datas) if len(datas) else (None, None)
        origem = "herdada do dataset"
    else:
        corte1 = corte2 = None
        origem = "calculada aqui (dataset ausente)"

    if corte1 is None:
        corte1, corte2 = cortes_temporais(df["data_sentenca"])

    # caso que nao esta no dataset (escape, fora da populacao) cai na particao
    # pela propria data, com os mesmos cortes
    df["particao"] = atribuir(df, corte1, corte2)
    mapa = dict(zip(df["caso_id"], df["particao"]))
    for p in pares:
        p["particao"] = herdada.get(p["caso_id"]) or mapa.get(p["caso_id"])
    return corte1, corte2, origem


INSTRUCAO_SIMPLES = (
    "Classifique o resultado do pedido de adicional de insalubridade neste "
    "trecho de sentenca trabalhista. Responda apenas com 'deferido' ou "
    "'indeferido'.")


def _formatos(par, alvo_simples):
    """
    O MESMO exemplo nos tres formatos que os provedores consomem.

    chat          messages[system,user,assistant] - APIs de fine-tuning
    alpaca        instruction/input/output        - LoRA local (axolotl, unsloth)
    texto_rotulo  texto/rotulo/label              - classificador (BERT, sklearn)

    Escrever os tres custa quase nada e evita que trocar de provedor vire uma
    reconversao manual do dataset.
    """
    msgs = par["registro"]["messages"]
    sistema, usuario, saida = (msgs[0]["content"], msgs[1]["content"],
                               msgs[2]["content"])
    # `usuario` leva instrucao e delimitadores, que o formato chat precisa e os
    # outros dois nao: em alpaca a instrucao vai em campo proprio, e o
    # classificador recebe texto puro. Repetir a instrucao dentro do `input`
    # ensinaria o modelo a esperar esse prefixo na inferencia.
    texto = par.get("texto") or usuario
    rotulo = par["rotulo"]
    return {
        "chat": {"messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
            {"role": "assistant", "content": saida}]},
        "alpaca": {
            "instruction": INSTRUCAO_SIMPLES if alvo_simples else sistema,
            "input": texto,
            "output": saida},
        "texto_rotulo": {
            "id": par["caso_id"], "texto": texto, "rotulo": rotulo,
            "label": 1 if rotulo == "deferido" else 0},
    }


def gravar(pares, saida, meta, formatos=("chat", "alpaca", "texto_rotulo"),
           alvo_simples=True):
    os.makedirs(saida, exist_ok=True)
    contagem, escritos = {}, []
    for particao, arquivo in ARQUIVOS.items():
        nome = Path(arquivo).stem
        selecao = [p for p in pares if p["particao"] == particao]
        contagem[particao] = len(selecao)
        for fmt in formatos:
            caminho = Path(saida) / f"{fmt}_{nome}.jsonl"
            with open(caminho, "w", encoding="utf-8") as f:
                for p in selecao:
                    f.write(json.dumps(_formatos(p, alvo_simples)[fmt],
                                       ensure_ascii=False) + "\n")
            escritos.append(caminho.name)

    meta["linhas"] = contagem
    meta["formatos"] = list(formatos)
    with open(Path(saida) / "manifesto.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(Path(saida) / "DATASET_CARD.md", "w", encoding="utf-8") as f:
        f.write(cartao(pares, contagem, meta))
    return contagem


def cartao(pares, contagem, meta):
    """Cartao do conjunto. Gerado a cada execucao, nunca escrito a mao."""
    def bloco(nome):
        p = [x for x in pares if x["particao"] == nome]
        if not p:
            return f"| {nome} | 0 | — | — |"
        dif = sum(1 for x in p if x["rotulo"] == "deferido") / len(p)
        datas = sorted(str(x["data_sentenca"])[:10] for x in p)
        return f"| {nome} | {len(p)} | {dif:.0%} | {datas[0]} a {datas[-1]} |"

    chars = sum(len(x["registro"]["messages"][1]["content"]) for x in pares)
    n = max(len(pares), 1)
    teste = [x for x in pares if x["particao"] == "teste"]
    base = (sum(1 for x in teste if x["rotulo"] == "deferido") / len(teste)
            if teste else float("nan"))
    piso = (f"{base:.0%}" if teste else
            "— (partição de teste não gerada; ver abaixo)")

    return f"""# Fine-tuning — resultado do pedido de insalubridade

Pares (trecho de sentença → resultado do pedido), gerados de
`{meta['fonte_do_texto_usada']}` por `gerar_finetune.py`.

**Gerado em:** {date.today().isoformat()} · **Versão:** {meta['versao']}

## Partições — divisão temporal, não aleatória

| Partição | Exemplos | Deferido | Período |
|---|---|---|---|
{bloco('treino')}
{bloco('calibracao')}
{bloco('teste')}

Cortes em {meta['corte_calibracao']} e {meta['corte_teste']}, **herdados do
dataset** (`{meta['origem_particao']}`). O corte cai em fronteira de data, não
de posição na lista: sentenças do mesmo dia nunca ficam em partições
diferentes.

Volume: ~{chars/4/1000:.0f} mil tokens. Entrada média: {chars//n} caracteres.

## Três formatos, mesmos dados

| Arquivo | Formato | Para |
|---|---|---|
| `chat_*.jsonl` | `{{"messages": [system, user, assistant]}}` | APIs de fine-tuning |
| `alpaca_*.jsonl` | `{{"instruction", "input", "output"}}` | LoRA local — axolotl, unsloth, peft |
| `texto_rotulo_*.jsonl` | `{{"texto", "rotulo", "label"}}` | classificador simples — BERT, sklearn |

## Limitação que não pode ser omitida

**Nenhum rótulo foi conferido contra leitura humana.** A origem é
`{meta['origem_rotulo']}`. Um modelo ajustado aqui aprende a imitar esses
rótulos, inclusive os erros deles — o teto de qualidade é a acurácia da fonte,
que ainda não foi medida.

Isso torna o conjunto útil para **prototipar o pipeline de fine-tuning**, não
para afirmar desempenho. A amostra do gold set está sorteada em
`dataset/data/gold_set.csv`; sem ela, qualquer métrica mede imitação.

## Desbalanceamento

A classe positiva domina. Um modelo que responda sempre "deferido" acerta
{piso} no teste. Compare contra essa linha de base, não contra 50%.

## Sobre a tarefa

Classificar o dispositivo é tarefa que **regra determinística já resolve** — foi
assim que a maior parte destes rótulos nasceu. O ganho real de um modelo de
linguagem está na extração das variáveis de conteúdo (laudo, grau, agente) a
partir da fundamentação, que regra não alcança. Esse segundo conjunto depende do
gold set: os campos aparecem em `campos_sem_referencia` no manifesto enquanto
não existirem.

## Privacidade

O texto vai como está na sentença, com identificadores mascarados
(`redacao={meta['redacao']}`). Mascarar CNJ e CPF **não é anonimização**: a
fundamentação de insalubridade descreve condição de saúde apurada em perícia.
Esta pasta não é versionada e não deve sair da máquina sem decisão explícita.
"""


def relatorio(contagem, cobertos, faltantes, meta, corte1, corte2):
    print("=" * 74)
    print("GERACAO DOS PARES DE FINE-TUNING")
    print("=" * 74)
    print(f"  fonte do rotulo : {meta['fonte_rotulo']}  ({meta['origem_rotulo']})")
    print(f"  tema            : {meta['tema']}")
    print(f"  redacao de id   : {'sim' if meta['redacao'] else 'NAO'}")
    print(f"  corte temporal  : {corte1.date()}  |  {corte2.date()}"
          f"   ({meta['origem_particao']})")

    print(f"\n  campos no alvo  : {', '.join(cobertos)}")
    if faltantes:
        print(f"  campos SEM referencia: {', '.join(faltantes)}")
        print("    Esses campos do schema de extracao nao existem na fonte de")
        print("    rotulo. O modelo ajustado nao vai aprender a produzi-los.")

    print(f"\n{'particao':<14}{'linhas':>8}   arquivos")
    for particao, arquivo in ARQUIVOS.items():
        nome = arquivo.replace(".jsonl", "")
        fmts = "  ".join(f"{f}_{nome}.jsonl" for f in meta.get("formatos", []))
        print(f"{particao:<14}{contagem[particao]:>8}   {fmts}")

    total = sum(contagem.values())
    print("\n" + "-" * 74)
    if meta["fonte_rotulo"] == "regra":
        print("AVISO: rotulo vindo da regra, nao de leitura humana. Este JSONL")
        print("  serve para exercitar o formato e o caminho de codigo. Ajustar um")
        print("  modelo sobre ele ensina os erros da regra com perfeicao.\n")
    if total < 200:
        print(f"AVISO: {total} pares no total. Abaixo disso o ajuste tende a")
        print("  decorar a amostra. Amplie o gold set antes de treinar de verdade.\n")
    print("O JSONL carrega o texto da sentenca. Nao versione, nao envie para")
    print("servico de terceiro sem decidir isso explicitamente.")


# ===========================================================================
def demo(caminho):
    """Banco falso com capitulos e gold set, para exercitar o gerador."""
    import random
    random.seed(5)
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    if Path(caminho).exists():
        Path(caminho).unlink()
    con = sqlite3.connect(caminho)
    con.executescript(Path("schema.sql").read_text(encoding="utf-8"))
    con.executescript("""
        CREATE TABLE IF NOT EXISTS capitulos (
            doc_id TEXT NOT NULL, caso_id TEXT, tema TEXT NOT NULL,
            titulo TEXT, texto TEXT NOT NULL, na_amostra INTEGER DEFAULT 0,
            PRIMARY KEY (doc_id, tema));
    """)

    conclusoes = ["insalubre", "nao_insalubre", "inconclusivo"]
    agentes = ["biologico", "quimico", "fisico"]
    for i in range(120):
        doc, caso = f"d{i:04d}", f"c{i:04d}"
        data = f"202{i % 5}-{(i % 12) + 1:02d}-15"
        conclusao = random.choice(conclusoes)
        agente = random.choice(agentes)
        resultado_esperado = "deferido" if conclusao == "insalubre" else "indeferido"
        con.execute("INSERT INTO documentos (doc_id, numero_cnj, orgao_julgador,"
                    " data_sentenca, tipo_decisao, julga_insalubridade,"
                    " arquivo_bruto, sha256, fonte) VALUES (?,?,?,?,?,?,?,?,?)",
                    (doc, f"{i:07d}-45.2022.5.16.0002", "1a VT Balsas", data,
                     "sentenca_merito", "sim", "", "", "demo"))
        con.execute("INSERT INTO casos (caso_id, numero_cnj, pedido, doc_id,"
                    " resultado_pedido, entra_no_modelo) VALUES (?,?,?,?,?,1)",
                    (caso, f"{i:07d}-45.2022.5.16.0002", "insalubridade", doc,
                     "deferido" if conclusao == "insalubre" else "indeferido"))
        con.execute("INSERT INTO capitulos (doc_id, caso_id, tema, titulo, texto)"
                    " VALUES (?,?,?,?,?)",
                    (doc, caso, "insalubridade", "DO ADICIONAL DE INSALUBRIDADE",
                     f"O laudo pericial nos autos {i:07d}-45.2022.5.16.0002 "
                     f"concluiu pela condicao {conclusao}, por exposicao a agente "
                     f"{agente}. O reclamante, CPF 123.456.789-00, exercia a "
                     f"funcao em contato habitual."))
        for campo, valor in (("laudo_conclusao", conclusao), ("agente", agente),
                             ("resultado_pedido", resultado_esperado)):
            con.execute("INSERT INTO gold_set (caso_id, campo, valor, anotador,"
                        " anotado_em) VALUES (?,?,?,?,?)",
                        (caso, campo, valor, "demo", data))
        # valores/ = o que a destilacao le. Sem isto o --demo so exercitava o
        # caminho do gold set, que nao e mais o padrao.
        resultado = resultado_esperado
        con.execute("INSERT INTO valores (caso_id, campo, valor, evidencia,"
                    " metodo, versao) VALUES (?,?,?,?,?,?)",
                    (caso, "resultado_pedido", resultado, "", "regra", "demo"))
        if i % 7 == 0:      # uma fatia anotada por modelo, como no corpus real
            con.execute("INSERT INTO valores (caso_id, campo, valor, evidencia,"
                        " metodo, versao) VALUES (?,?,?,?,?,?)",
                        (caso, "resultado_pedido", resultado, "", "llm", "demo"))
    con.commit()
    print(f"banco falso em {caminho}: 120 capitulos com gold set\n")
    return con


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--banco", default="../data/juripredict.db")
    ap.add_argument("--dataset", default="../data/juripredict.csv",
                    help="de onde herdar a particao temporal, para o corte ser "
                         "o mesmo do dataset")
    ap.add_argument("--saida", default="../../finetune")
    ap.add_argument("--tema", default="insalubridade", choices=sorted(SCHEMAS))
    ap.add_argument("--fonte", default="llm", choices=("llm", "gold", "regra"),
                    help="llm = destilacao (padrao); gold = so anotacao humana")
    ap.add_argument("--gold", default="../data/gold_set.csv",
                    help="planilha do gold_set.py, se a tabela estiver vazia")
    ap.add_argument("--forcar", action="store_true",
                    help="libera --fonte regra")
    ap.add_argument("--texto", default="dispositivo",
                    choices=("dispositivo", "recorte"),
                    help="dispositivo = de onde o rotulo saiu (padrao); "
                         "recorte = fundamentacao + dispositivo em volta do tema")
    ap.add_argument("--alvo", default="simples", choices=("simples", "estruturado"),
                    help="simples = deferido/indeferido; estruturado = JSON")
    ap.add_argument("--formato", default="todos",
                    choices=("todos", "chat", "alpaca", "texto_rotulo"))
    ap.add_argument("--sem-redacao", action="store_true",
                    help="mantem CNJ e CPF no texto exportado")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()

    if a.fonte == "regra" and not a.forcar:
        sys.exit("--fonte regra treina o modelo so nos casos que a regra sabe "
                 "resolver,\ne nos erros dela. Se e isso mesmo, repita com "
                 "--forcar.\nO padrao (--fonte llm) destila regra + anotacao "
                 "por modelo.")

    if a.demo:
        con = demo("../data/demo_finetune.db")
        a.saida = "../data/demo_finetune"
    else:
        if not Path(a.banco).exists():
            sys.exit(f"banco {a.banco} nao existe. Rode processar.py antes.")
        con = sqlite3.connect(a.banco)
    con.row_factory = sqlite3.Row

    capitulos, fontes_texto = carregar_capitulos(con, a.tema, fonte=a.texto)
    if not capitulos:
        sys.exit(f"nenhum texto do tema '{a.tema}' no banco. Rode processar.py "
                 f"antes.")

    gold, origem_gold = rotulos_do_gold(con, a.gold)
    if a.fonte == "gold":
        rotulos, origem, por_caso = gold, origem_gold, {}
        if not rotulos:
            sys.exit("gold set vazio. Com --fonte gold ele e pre-condicao:\n"
                     "    python gold_set.py amostrar --n 50\n"
                     "    (anote a planilha a mao)\n"
                     "    python gold_set.py comparar --arquivo ../data/gold_set.csv")
    elif a.fonte == "llm":
        rotulos, por_caso, origem = rotulos_por_destilacao(con)
    else:
        rotulos, origem = rotulos_da_regra(con)
        por_caso = {}
    con.close()

    pares, cobertos, faltantes = montar_pares(
        capitulos, rotulos, a.tema, not a.sem_redacao,
        alvo_simples=(a.alvo == "simples"))
    if not pares:
        sys.exit("nenhum caso com texto E rotulo ao mesmo tempo. Confira se a "
                 "amostra do\ngold set saiu dos mesmos casos que tem capitulo "
                 "recortado.")

    corte1, corte2, origem_particao = particionar(
        pares, None if a.demo else a.dataset)

    # A escolha metodologica deste script: TREINAR por destilacao, MEDIR contra
    # anotacao humana. Por isso a particao de teste so sai se o gold set
    # existir - um teste rotulado pelo mesmo processo que gerou o treino mede o
    # proprio ajuste, nao a qualidade da extracao.
    sem_gold_no_teste = a.fonte != "gold" and not gold
    if sem_gold_no_teste:
        pares = [p for p in pares if p["particao"] != "teste"]

    meta = {
        "versao": VERSAO_FINETUNE,
        "versao_prompt": VERSAO_PROMPT,
        "tema": a.tema,
        "fonte_rotulo": a.fonte,
        "origem_rotulo": origem,
        "origem_gold": origem_gold,
        "teste_suprimido_por_falta_de_gold": sem_gold_no_teste,
        "fonte_do_texto": fontes_texto,
        "fonte_do_texto_usada": a.texto,
        "alvo": a.alvo,
        "campos": cobertos,
        "campos_sem_referencia": faltantes,
        "redacao": not a.sem_redacao,
        "origem_particao": origem_particao,
        "corte_calibracao": str(corte1.date()),
        "corte_teste": str(corte2.date()),
    }
    if por_caso:
        meta["rotulos_por_metodo"] = {
            m: sum(1 for p in pares if por_caso.get(p["caso_id"]) == m)
            for m in ("regra", "llm")}
    formatos = (("chat", "alpaca", "texto_rotulo") if a.formato == "todos"
                else (a.formato,))
    contagem = gravar(pares, a.saida, meta, formatos,
                      alvo_simples=(a.alvo == "simples"))
    relatorio(contagem, cobertos, faltantes, meta, corte1, corte2)
    if sem_gold_no_teste:
        print("\nParticao de TESTE nao gerada: exige gold set (anotacao humana).")
        print("  python gold_set.py amostrar --n 50   <- amostre TAMBEM entre os")
        print("  casos resolvidos por rotular_ambiguos.py, nao so entre os faceis.")
    print(f"\n{a.saida}/  gravado.")
