"""
Coletor da API Publica do DataJud. E a peca que faltava no pipeline.

    # 1. PRIMEIRO ISTO: descobre o que a API devolve de verdade
    python coletar_datajud.py testar --tribunal trt16

    # 2. conta quantos processos existem no recorte, sem baixar
    python coletar_datajud.py contar --tribunal trt16 --assunto <codigo_tpu>

    # 3. coleta e grava
    python coletar_datajud.py coletar --tribunal trt16 --assunto <codigo_tpu> \\
        --de 2020 --ate 2026 --banco ../data/juripredict.db

    # sem rede: exercita o parsing e a gravacao com resposta fabricada
    python coletar_datajud.py demo

A chave publica do CNJ vai em variavel de ambiente, nunca no codigo:

    export DATAJUD_API_KEY='APIKey <chave da wiki do CNJ>'

EXECUTADO contra a API em 2026-09. O que a resposta real mostrou, e que a
versao escrita a partir da documentacao errava:

  - `grau` precisa ser consultado como `grau.keyword`; como `grau` devolve zero;
  - o indice mistura primeiro e segundo grau (339.021 e 90.086 documentos), e
    sem filtro entram recursos ordinarios num dataset de sentencas de 1o grau;
  - o assunto "Adicional de Insalubridade" e 13875, nao 1663 - codigo que nao
    existe neste indice;
  - `numeroProcesso` vem SEM mascara, e o resto do pipeline usa a forma
    mascarada: unir as bases sem converter da zero interseccao.
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = "https://api-publica.datajud.cnj.jus.br"
PAUSA = 1.0
TENTATIVAS = 4

# Classificacao do desfecho pelo NOME do movimento. Mais robusto que o codigo,
# que pode variar entre versoes da TPU. Ordem importa.
PADROES_DESFECHO = [
    ("acordo", r"homologa[çc][ãa]o\s+de\s+(acordo|transa[çc][ãa]o)|concilia[çc][ãa]o"),
    ("extinto_sem_merito", r"sem\s+resolu[çc][ãa]o\s+do\s+m[ée]rito"),
    ("parcial", r"proced[êe]ncia\s+em\s+parte|parcialmente\s+procedente"),
    ("improcedente", r"improced[êe]ncia"),
    ("procedente", r"proced[êe]ncia"),
]
RE_SENTENCA = re.compile(r"julgamento|senten[çc]a|proced[êe]ncia", re.IGNORECASE)


def cabecalhos():
    # O .env da raiz e a fonte, como no extrair_llm.py. Sem esta chamada o
    # script so enxergava variavel exportada no shell, e a chave no .env - que
    # e onde o projeto manda guarda-la - era ignorada em silencio.
    from extrair_llm import carregar_env
    carregar_env()

    chave = os.environ.get("DATAJUD_API_KEY", "").strip()
    if not chave:
        sys.exit("DATAJUD_API_KEY vazia.\n\n"
                 "Coloque no .env da raiz do projeto:\n"
                 "    DATAJUD_API_KEY=<chave publica da wiki do CNJ>\n\n"
                 "A chave e publica e esta em https://datajud-wiki.cnj.jus.br/"
                 "api-publica/acesso")
    if not chave.lower().startswith("apikey"):
        chave = f"APIKey {chave}"
    return {"Authorization": chave, "Content-Type": "application/json"}


def consultar(tribunal, corpo):
    import requests
    url = f"{BASE}/api_publica_{tribunal}/_search"
    for tentativa in range(1, TENTATIVAS + 1):
        r = requests.post(url, headers=cabecalhos(), json=corpo, timeout=60)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 502, 503, 504) and tentativa < TENTATIVAS:
            espera = 2 ** tentativa
            print(f"  HTTP {r.status_code}; nova tentativa em {espera}s")
            time.sleep(espera)
            continue
        sys.exit(f"HTTP {r.status_code}: {r.text[:400]}")


# Medido contra a API em 2026-09: o indice do TRT-16 tem 339.021 documentos de
# primeiro grau e 90.086 de segundo. Sem este filtro, recursos ordinarios
# entram num dataset que so admite sentenca de 1o grau (invariante I1).
#
# E precisa ser `grau.keyword`: `{"term": {"grau": "G1"}}` devolve ZERO, porque
# o campo e analisado como texto.
FILTRO_PRIMEIRO_GRAU = {"term": {"grau.keyword": "G1"}}

# 13875 = "Adicional de Insalubridade", confirmado contra a API. A docstring
# original dizia 1663, codigo que nao existe neste indice e devolvia zero.
ASSUNTO_INSALUBRIDADE = 13875


def mascarar_cnj(numero):
    """
    00177638620265160016 -> 0017763-86.2026.5.16.0016

    O DataJud devolve o numero sem mascara; o FALCAO e todo o resto do pipeline
    usam a forma mascarada. Unir as duas bases sem isto da zero interseccao.
    """
    if not numero:
        return None
    d = re.sub(r"\D", "", str(numero))
    if len(d) != 20:
        return str(numero)
    return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"


def filtro(assunto, de, ate, so_primeiro_grau=True):
    f = []
    if so_primeiro_grau:
        f.append(FILTRO_PRIMEIRO_GRAU)
    if assunto:
        f.append({"term": {"assuntos.codigo": assunto}})
    if de or ate:
        faixa = {}
        if de:
            faixa["gte"] = f"{de}-01-01"
        if ate:
            faixa["lte"] = f"{ate}-12-31"
        f.append({"range": {"dataAjuizamento": faixa}})
    return {"bool": {"filter": f}} if f else {"match_all": {}}


# ---------------------------------------------------------------- comandos
def testar(tribunal):
    """Mostra a estrutura real de um documento. Rode isto antes de tudo."""
    resp = consultar(tribunal, {"size": 1, "query": {"match_all": {}}})
    total = resp.get("hits", {}).get("total", {})
    hits = resp.get("hits", {}).get("hits", [])
    print(f"conexao OK · total no indice: {total}")
    if not hits:
        sys.exit("indice vazio ou filtro invalido")

    src = hits[0]["_source"]
    print("\ncampos de primeiro nivel:")
    for k, v in src.items():
        if isinstance(v, list):
            amostra = v[0] if v else None
            print(f"  {k:<28} lista[{len(v)}]  ex: {json.dumps(amostra, ensure_ascii=False)[:110]}")
        elif isinstance(v, dict):
            print(f"  {k:<28} objeto     {json.dumps(v, ensure_ascii=False)[:110]}")
        else:
            print(f"  {k:<28} {str(v)[:110]}")

    print("\nconfira se existem: numeroProcesso, orgaoJulgador, assuntos,")
    print("movimentos, dataAjuizamento. Se algum faltar ou tiver outro nome,")
    print("ajuste normalizar() antes de coletar.")
    # em ../data/, que nao e versionado - nao no diretorio de codigo
    destino = Path("../data/datajud_amostra.json")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(src, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print(f"\ndocumento completo em {destino}")


def contar(tribunal, assunto, de, ate):
    resp = consultar(tribunal, {"size": 0, "track_total_hits": True,
                                "query": filtro(assunto, de, ate)})
    total = resp["hits"]["total"]
    n = total["value"] if isinstance(total, dict) else total
    print(f"{n} processos no recorte")
    if isinstance(total, dict) and total.get("relation") == "gte":
        print("  (valor minimo; o indice trunca a contagem)")
    return n


def normalizar(src):
    """Documento da API -> linha tabular. AJUSTE APOS RODAR `testar`."""
    movs = src.get("movimentos") or []
    nomes = " | ".join((m.get("nome") or "") for m in movs).lower()
    desfecho = "indefinido"
    for rotulo, padrao in PADROES_DESFECHO:
        if re.search(padrao, nomes):
            desfecho = rotulo
            break

    datas = sorted(m.get("dataHora") for m in movs
                   if m.get("dataHora") and RE_SENTENCA.search(m.get("nome") or ""))

    orgao = src.get("orgaoJulgador") or {}
    return {
        "numero_cnj": mascarar_cnj(src.get("numeroProcesso")),
        "grau": src.get("grau"),
        "classe": (src.get("classe") or {}).get("nome"),
        "orgao_julgador": orgao.get("nome"),
        "codigo_orgao": orgao.get("codigo"),
        "municipio_ibge": orgao.get("codigoMunicipioIBGE"),
        "data_ajuizamento": src.get("dataAjuizamento"),
        "assuntos": ",".join(str((a or {}).get("codigo")) for a in (src.get("assuntos") or [])),
        "desfecho_movimento": desfecho,
        "n_movimentos": len(movs),
        "n_julgamentos": len(datas),
        "data_primeiro_julgamento": datas[0] if datas else None,
        "data_ultimo_julgamento": datas[-1] if datas else None,
    }


def garantir_tabela(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS datajud (
        numero_cnj TEXT PRIMARY KEY, grau TEXT, classe TEXT,
        orgao_julgador TEXT, codigo_orgao INTEGER, municipio_ibge INTEGER,
        data_ajuizamento TEXT, assuntos TEXT, desfecho_movimento TEXT,
        n_movimentos INTEGER, n_julgamentos INTEGER,
        data_primeiro_julgamento TEXT, data_ultimo_julgamento TEXT,
        coletado_em TEXT);
    CREATE INDEX IF NOT EXISTS idx_dj_orgao ON datajud(orgao_julgador);
    """)


def gravar(con, linhas):
    garantir_tabela(con)
    agora = datetime.now().isoformat(timespec="seconds")
    con.executemany(
        "INSERT OR REPLACE INTO datajud VALUES "
        "(:numero_cnj,:grau,:classe,:orgao_julgador,:codigo_orgao,:municipio_ibge,"
        ":data_ajuizamento,:assuntos,:desfecho_movimento,:n_movimentos,"
        ":n_julgamentos,:data_primeiro_julgamento,:data_ultimo_julgamento,:coletado_em)",
        [{**l, "coletado_em": agora} for l in linhas])
    con.commit()


def coletar(tribunal, assunto, de, ate, banco, teto):
    os.makedirs(os.path.dirname(banco) or ".", exist_ok=True)
    con = sqlite3.connect(banco)
    garantir_tabela(con)

    total, ultimo, lote = 0, None, []
    while total < teto:
        corpo = {"size": 100, "sort": [{"@timestamp": {"order": "asc"}}],
                 "query": filtro(assunto, de, ate)}
        if ultimo:
            corpo["search_after"] = ultimo
        hits = consultar(tribunal, corpo).get("hits", {}).get("hits", [])
        if not hits:
            break
        lote = [normalizar(h["_source"]) for h in hits]
        gravar(con, lote)
        total += len(hits)
        ultimo = hits[-1].get("sort")
        print(f"  {total} processos gravados")
        time.sleep(PAUSA)

    resumo(con)
    con.close()


def resumo(con):
    print("\n" + "=" * 60)
    print("BASE DATAJUD")
    print("=" * 60)
    n = con.execute("SELECT COUNT(*) FROM datajud").fetchone()[0]
    print(f"  processos: {n}")
    print("\n  desfecho pelos movimentos")
    for d, c in con.execute("SELECT desfecho_movimento, COUNT(*) FROM datajud "
                            "GROUP BY 1 ORDER BY 2 DESC"):
        print(f"    {d:<22}{c:>7}{c/max(n,1):>7.0%}")
    print("\n  Taxas de acordo e extincao saem daqui: sao as classes de escape")
    print("  reportadas ao lado de cada taxa-base.")

    multi = con.execute("SELECT COUNT(*) FROM datajud WHERE n_julgamentos > 1").fetchone()[0]
    print(f"\n  processos com mais de um julgamento: {multi} ({multi/max(n,1):.0%})")
    print("  e o que permite marcar ordem_sentenca = primeira/posterior")


# ---------------------------------------------------------------- demo
RESPOSTA_FALSA = {"hits": {"total": {"value": 3}, "hits": [
    {"sort": [1], "_source": {
        "numeroProcesso": "00001234520225160002", "grau": "G1",
        "classe": {"codigo": 985, "nome": "Ação Trabalhista - Rito Ordinário"},
        "orgaoJulgador": {"codigo": 21538, "nome": "2ª Vara do Trabalho de Balsas",
                          "codigoMunicipioIBGE": 2101400},
        "dataAjuizamento": "2022-03-14T00:00:00.000Z",
        "assuntos": [{"codigo": 13875, "nome": "Adicional de Insalubridade"}],
        "movimentos": [
            {"codigo": 26, "nome": "Distribuição", "dataHora": "2022-03-14T10:00:00.000Z"},
            {"codigo": 219, "nome": "Procedência em Parte", "dataHora": "2023-08-02T15:00:00.000Z"}]}},
    {"sort": [2], "_source": {
        "numeroProcesso": "00005678920215160001", "grau": "G1",
        "classe": {"codigo": 985, "nome": "Ação Trabalhista - Rito Ordinário"},
        "orgaoJulgador": {"codigo": 21537, "nome": "1ª Vara do Trabalho de Balsas",
                          "codigoMunicipioIBGE": 2101400},
        "dataAjuizamento": "2021-07-02T00:00:00.000Z",
        "assuntos": [{"codigo": 13875, "nome": "Adicional de Insalubridade"}],
        "movimentos": [
            {"codigo": 26, "nome": "Distribuição", "dataHora": "2021-07-02T09:00:00.000Z"},
            {"codigo": 466, "nome": "Homologação de Acordo", "dataHora": "2022-01-20T11:00:00.000Z"}]}},
    {"sort": [3], "_source": {
        "numeroProcesso": "00009991120235160003", "grau": "G1",
        "classe": {"codigo": 985, "nome": "Ação Trabalhista - Rito Ordinário"},
        "orgaoJulgador": {"codigo": 21540, "nome": "1ª Vara do Trabalho de Imperatriz",
                          "codigoMunicipioIBGE": 2105302},
        "dataAjuizamento": "2023-02-10T00:00:00.000Z",
        "assuntos": [{"codigo": 13875, "nome": "Adicional de Insalubridade"}],
        "movimentos": [
            {"codigo": 26, "nome": "Distribuição", "dataHora": "2023-02-10T08:00:00.000Z"},
            {"codigo": 220, "nome": "Improcedência", "dataHora": "2024-05-11T14:00:00.000Z"},
            {"codigo": 219, "nome": "Procedência em Parte", "dataHora": "2025-02-03T16:00:00.000Z"}]}},
]}}


def demo(banco="../data/demo_datajud.db"):
    os.makedirs(os.path.dirname(banco) or ".", exist_ok=True)
    con = sqlite3.connect(banco)
    linhas = [normalizar(h["_source"]) for h in RESPOSTA_FALSA["hits"]["hits"]]
    gravar(con, linhas)
    print("parsing e gravacao exercitados com resposta fabricada\n")
    for l in linhas:
        print(f"  {l['numero_cnj']}  {l['orgao_julgador']:<32}"
              f"{l['desfecho_movimento']:<20}julg={l['n_julgamentos']}")
    resumo(con)
    con.close()
    print("\nA rede NAO foi testada. Rode `testar` contra a API antes de coletar.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("testar");  t.add_argument("--tribunal", default="trt16")
    c = sub.add_parser("contar")
    c.add_argument("--tribunal", default="trt16")
    c.add_argument("--assunto", type=int)
    c.add_argument("--de", type=int); c.add_argument("--ate", type=int)

    k = sub.add_parser("coletar")
    k.add_argument("--tribunal", default="trt16")
    k.add_argument("--assunto", type=int, default=ASSUNTO_INSALUBRIDADE)
    k.add_argument("--de", type=int, default=2020)
    k.add_argument("--ate", type=int, default=2026)
    k.add_argument("--banco", default="../data/juripredict.db")
    k.add_argument("--teto", type=int, default=50000)

    sub.add_parser("demo")

    a = ap.parse_args()
    if a.cmd == "testar":
        testar(a.tribunal)
    elif a.cmd == "contar":
        contar(a.tribunal, a.assunto, a.de, a.ate)
    elif a.cmd == "coletar":
        coletar(a.tribunal, a.assunto, a.de, a.ate, a.banco, a.teto)
    else:
        demo()