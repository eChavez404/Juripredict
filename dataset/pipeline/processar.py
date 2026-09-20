"""
Espinha do pipeline. Liga as pecas que ja existiam ao banco:

    bruto (html/pdf/txt) -> texto -> secoes -> rotulo por regra -> banco

Sem este script, cortar_secoes.py e rotular_por_regra.py sao funcoes soltas e
extrair_llm.py nao encontra a tabela 'capitulos' de onde le.

    python processar.py --entrada ../data/normalized --banco ../data/juripredict.db
    python processar.py --demo            # gera sentencas falsas e roda tudo
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from cortar_secoes import cortar
from rotular_por_regra import rotular, resultado_global, CORRIGE_COERENCIA

VERSAO_REGRA = "regra-2026.09"

# Classificacao do evento processual. O FALCAO marca tudo como
# tipoDocumento="Sentenca" — 776 dos 787 documentos —, inclusive liquidacao e
# embargos, entao esse campo nao serve. Ja `classe` serve, e e usada primeiro
# em classificar_evento(); os padroes abaixo cobrem o resto, e saem de
# documentos reais do TRT-16, nao de suposicao.
PADROES_EVENTO = [
    ("LIQUIDACAO", re.compile(
        r"impugna[çc][ãa]o\s+aos\s+c[áa]lculos|embargos\s+[àa]\s+execu[çc][ãa]o"
        r"|c[áa]lculos\s+de\s+liquida[çc][ãa]o|excesso\s+de\s+execu[çc][ãa]o",
        re.IGNORECASE)),
    ("EMBARGOS_DECLARACAO", re.compile(
        r"embargos\s+(de\s+)?declarat[óo]rios|embargos\s+de\s+declara[çc][ãa]o",
        re.IGNORECASE)),
    ("EXECUCAO", re.compile(
        r"cumprimento\s+de\s+senten[çc]a|carta\s+de\s+senten[çc]a", re.IGNORECASE)),
    ("HOMOLOGATORIA", re.compile(
        r"homologo\s+(o\s+)?acordo|homologa[çc][ãa]o\s+de\s+acordo", re.IGNORECASE)),
]


# Classe processual de execucao. Vem do tribunal, nao do texto: quando ela diz
# cumprimento de sentenca, nao ha o que interpretar.
#
# Ja foi tentado, no lugar disto, ampliar PADROES_EVENTO com termos que remetem
# a uma sentenca anterior ("sentenca meritoria", "base de apuracao", "habilitar
# judicialmente"). Medido contra o corpus, reclassificava ZERO documentos. E os
# termos vizinhos que pareciam equivalentes sao armadilhas: "planilha de
# calculos" casa em 62 sentencas de merito normais, "coisa julgada" em 37,
# "titulo executivo" em 18, e um titulo de secao "LIQUIDACAO" em 169.
CLASSES_EXECUCAO = {"CumSen", "CumPrSe"}

# Classes coletivas: acao de cumprimento, acao civil publica, acao de
# cumprimento de sentenca coletiva. Uma decisao dessas alcanca os substituidos
# da categoria inteira - a unidade nao e o pedido de um trabalhador.
CLASSES_COLETIVAS = {"ACC", "ACPCiv", "ACum"}

# Quem propos a acao. Sindicato como REU, ou citado numa CCT, e comum em acao
# individual - por isso so vale a linha AUTOR/RECLAMANTE do cabecalho, e nao a
# mencao a sindicato em qualquer lugar do texto: essa versao ampla marcava 12
# acoes individuais como coletivas.
RE_AUTOR = re.compile(r"(?:AUTOR|EXEQUENTE|RECLAMANTE)S?:\s*([^\n]{0,90})",
                      re.IGNORECASE)
ENTE_COLETIVO = re.compile(
    r"^\s*(?:SIND\b|SINDICATO|FEDERA[ÇC][ÃA]O|ASSOCIA[ÇC][ÃA]O"
    r"|MINIST[ÉE]RIO\s+P[ÚU]BLICO)", re.IGNORECASE)


def autor_e_coletivo(texto, classe=None) -> int:
    if classe in CLASSES_COLETIVAS:
        return 1
    m = RE_AUTOR.search(texto[:2500])
    return 1 if (m and ENTE_COLETIVO.match(m.group(1).strip())) else 0

# Cabecalho: o titulo do documento, entre as partes e o relatorio. E ali que a
# decisao se identifica ("SENTENCA - EMBARGOS DECLARATORIOS", "DECISAO DE
# IMPUGNACAO AOS CALCULOS").
CABECALHO = 900

# Linguagem de quem julga um INCIDENTE, nao o merito da acao. Serve de segunda
# opiniao quando o marcador aparece fora do cabecalho.
DECIDE_INCIDENTE = re.compile(
    r"conhe[çc]o\s+(?:d[oe]s?\s+)?embargos|acolho\s+os\s+embargos"
    r"|rejeito\s+os\s+embargos|dou\s+provimento\s+aos\s+embargos"
    r"|julg[áa]-los|impugna[çc][õo]es\s+aos\s+c[áa]lculos"
    r"|homologo\s+os\s+c[áa]lculos", re.IGNORECASE)


def classificar_evento(texto, dispositivo, classe=None):
    """
    MERITO_PRIMEIRO_GRAU ou o tipo de decisao posterior.

    Tres fontes, em ordem de confiabilidade:

      1. A CLASSE processual do manifesto. CumSen e cumprimento de sentenca -
         nao existe merito de primeiro grau ali. Sao 7 casos que a leitura do
         texto deixava entrar no dataset.

      2. O CABECALHO do documento, onde a decisao se nomeia. Marcador ali e
         tratado como definitivo.

      3. Marcador fora do cabecalho, que exige confirmacao no dispositivo. Sem
         isso, 64 sentencas de merito eram descartadas por citarem embargos no
         boilerplate da correcao monetaria ("seja em decorrencia de decisao em
         Embargos de Declaracao") ou por advertirem contra embargos
         protelatorios. Nenhuma delas julga incidente nenhum.
    """
    if not CORRIGE_COERENCIA:
        # comportamento da v1.0: marcador em qualquer lugar dos 3000 primeiros
        # caracteres ou do dispositivo, sem consultar a classe processual
        amostra = texto[:3000] + "\n" + (dispositivo or "")
        for rotulo, padrao in PADROES_EVENTO:
            if padrao.search(amostra):
                return rotulo
        return "MERITO_PRIMEIRO_GRAU"

    if classe in CLASSES_EXECUCAO:
        return "EXECUCAO"

    cabecalho = texto[:CABECALHO]
    for rotulo, padrao in PADROES_EVENTO:
        if padrao.search(cabecalho):
            return rotulo

    resto = texto[CABECALHO:3000] + "\n" + (dispositivo or "")
    for rotulo, padrao in PADROES_EVENTO:
        if padrao.search(resto) and DECIDE_INCIDENTE.search(dispositivo or ""):
            return rotulo
    return "MERITO_PRIMEIRO_GRAU"


TEMAS_ALVO = ("insalubridade",)   # periculosidade entra quando o recorte abrir


# ---------------------------------------------------------------- texto
def extrair_texto(caminho: Path) -> str:
    ext = caminho.suffix.lower()
    if ext in (".txt", ".text"):
        return caminho.read_text(encoding="utf-8", errors="replace")
    if ext in (".html", ".htm"):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            sys.exit("instale beautifulsoup4 para processar HTML")
        return BeautifulSoup(caminho.read_text(encoding="utf-8", errors="replace"),
                            "html.parser").get_text("\n")
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            sys.exit("instale pymupdf para processar PDF")
        with fitz.open(caminho) as doc:
            return "\n".join(p.get_text() for p in doc)
    raise ValueError(f"extensao nao suportada: {ext}")


# ------------------------------------------------------------ metadados
# O FALCAO ja devolve numeroProcesso, orgaoJulgadorPorExtenso e dataJulgamento,
# e o coletor gravou tudo no manifest. Extrair isso de novo por regex sobre o
# texto e trocar dado exato por adivinhacao — foi o que produziu orgao nulo em
# metade dos documentos e datas de outros trechos da sentenca.
#
# Agora o manifest e a fonte. A regex fica so como ultimo recurso.

RE_CNJ = re.compile(r"\b(\d{7}-?\d{2}\.?\d{4}\.?5\.?\d{2}\.?\d{4})\b")


def abrir_manifest(caminho):
    if not caminho or not Path(caminho).exists():
        return {}
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    try:
        linhas = con.execute(
            "SELECT id_sentenca, numero_cnj, orgao_julgador, data_julgamento, "
            "       classe, tipo_documento FROM documentos").fetchall()
    except sqlite3.OperationalError:
        con.close()
        return {}
    con.close()
    return {l["id_sentenca"]: dict(l) for l in linhas}


def _data_iso(valor):
    """O FALCAO manda dd/mm/aaaa."""
    if not valor:
        return None
    v = str(valor).strip()
    if "/" in v:
        partes = v.split("/")
        if len(partes) == 3:
            d, m, a = partes
            return f"{a}-{m.zfill(2)}-{d.zfill(2)}"
    return v[:10] or None


def metadados(texto, nome_arquivo, manifest):
    """Manifest primeiro; regex so se o documento nao estiver la."""
    reg = manifest.get(nome_arquivo)
    if reg:
        return {
            "numero_cnj": reg.get("numero_cnj") or nome_arquivo,
            "orgao_julgador": reg.get("orgao_julgador"),
            "data_sentenca": _data_iso(reg.get("data_julgamento")),
            "classe": reg.get("classe"),
            "tipo_documento_falcao": reg.get("tipo_documento"),
            "origem": "manifest",
        }

    cnj = RE_CNJ.search(texto)
    return {
        "numero_cnj": cnj.group(1) if cnj else nome_arquivo,
        "orgao_julgador": None,
        "data_sentenca": None,
        "classe": None,
        "tipo_documento_falcao": None,
        "origem": "regex",
    }


# ------------------------------------------------------------------ banco
def abrir(banco, schema="schema.sql"):
    os.makedirs(os.path.dirname(banco) or ".", exist_ok=True)
    con = sqlite3.connect(banco)
    con.executescript(Path(schema).read_text(encoding="utf-8"))
    con.executescript("""
    CREATE TABLE IF NOT EXISTS capitulos (
        doc_id TEXT NOT NULL, caso_id TEXT, tema TEXT NOT NULL,
        titulo TEXT, texto TEXT NOT NULL, na_amostra INTEGER DEFAULT 0,
        PRIMARY KEY (doc_id, tema));
    """)
    return con


def gravar_valor(con, caso_id, campo, valor, evidencia, metodo, versao):
    con.execute(
        "INSERT OR REPLACE INTO valores "
        "(caso_id, campo, valor, evidencia, metodo, versao, extraido_em) "
        "VALUES (?,?,?,?,?,?,?)",
        (caso_id, campo, valor, (evidencia or "")[:400], metodo, versao,
         datetime.now().isoformat(timespec="seconds")))


# ------------------------------------------------------------------ pipeline
def processar(entrada, banco, schema, manifest_path=None):
    con = abrir(banco, schema)
    manifest = abrir_manifest(manifest_path)
    print(f"manifest: {len(manifest)} documentos indexados\n"
          if manifest else "manifest ausente — metadados pelo texto\n")
    arquivos = sorted(p for p in Path(entrada).rglob("*")
                      if p.suffix.lower() in (".txt", ".html", ".htm", ".pdf"))
    if not arquivos:
        sys.exit(f"nenhum documento em {entrada}")

    cont = {"docs": 0, "sem_secao": 0, "sem_capitulo": 0, "casos": 0,
            "via_manifest": 0, "via_regex": 0, "sem_mencao": 0}
    estrategias, resultados, eventos = {}, {}, {}

    for caminho in arquivos:
        texto = extrair_texto(caminho)
        s = cortar(texto)
        meta = metadados(texto, caminho.stem, manifest)
        cont["via_manifest" if meta["origem"] == "manifest" else "via_regex"] += 1
        doc_id = hashlib.sha1(caminho.name.encode()).hexdigest()[:16]

        estrategias[s.estrategia] = estrategias.get(s.estrategia, 0) + 1
        if not s.dispositivo:
            cont["sem_secao"] += 1

        julga = "sim" if any(c.tema in TEMAS_ALVO for c in s.capitulos) else "nao"
        con.execute(
            "INSERT OR REPLACE INTO documentos (doc_id, numero_cnj, orgao_julgador,"
            " data_sentenca, classe, tipo_documento, autor_coletivo,"
            " tipo_decisao, julga_insalubridade, ordem_sentenca,"
            " arquivo_bruto, sha256, estrategia_corte, coletado_em, fonte)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc_id, meta["numero_cnj"], meta["orgao_julgador"],
             meta["data_sentenca"], meta["classe"], meta["tipo_documento_falcao"],
             autor_e_coletivo(texto, meta["classe"]),
             "sentenca_merito", julga, None,
             str(caminho),
             hashlib.sha256(caminho.read_bytes()).hexdigest(),
             s.estrategia, datetime.now().isoformat(timespec="seconds"), "local"))
        cont["docs"] += 1

        evento = classificar_evento(texto, s.dispositivo, meta["classe"])
        eventos[evento] = eventos.get(evento, 0) + 1

        for tema in TEMAS_ALVO:
            cap = s.capitulo_de(tema)
            if cap is None:
                cont["sem_capitulo"] += 1

            # O rotulo vem do DISPOSITIVO, nao do capitulo. Exigir capitulo
            # descartava sentencas cujo dispositivo defere o pedido com
            # clareza, so porque a fundamentacao nao tinha titulo proprio.
            if not s.dispositivo:
                continue

            caso_id = f"{doc_id}:{tema}"
            # a fundamentacao entra para permitir inferir o indeferimento
            # quando o dispositivo julga improcedente sem nomear o pedido
            r = rotular(s.dispositivo, tema, s.fundamentacao)

            # Dois casos diferentes sob o mesmo rotulo, e so um deve sumir:
            #
            #   sem evidencia  o tema nao aparece no documento. Nao ha pedido a
            #                  registrar, e criar linha para cada sentenca do
            #                  corpus so encheria a tabela de vazio.
            #   com evidencia  a regra LEU o dispositivo e decidiu que a mencao
            #                  nao e um pedido - base de reflexo, citacao de
            #                  precedente. Isso e uma decisao de exclusao, e o
            #                  invariante I1 manda registra-la, nao apaga-la.
            #
            # Antes os dois sumiam juntos, e 36 exclusoes decididas pela regra
            # viravam apenas um contador no relatorio.
            if r.resultado_pedido == "nao_mencionado" and cap is None:
                cont["sem_mencao"] += 1
                if not r.trecho:
                    continue

            resultados[r.resultado_pedido] = resultados.get(r.resultado_pedido, 0) + 1

            entra = 1 if (r.resultado_pedido in ("deferido", "indeferido")
                          and evento == "MERITO_PRIMEIRO_GRAU") else 0
            motivo = None
            if not entra:
                motivo = (evento if evento != "MERITO_PRIMEIRO_GRAU"
                          else r.resultado_pedido)

            con.execute(
                "INSERT OR REPLACE INTO casos (caso_id, numero_cnj, pedido, doc_id,"
                " resultado_pedido, grau_deferido, resultado_global, entra_no_modelo,"
                " motivo_exclusao) VALUES (?,?,?,?,?,?,?,?,?)",
                (caso_id, meta["numero_cnj"], tema, doc_id,
                 r.resultado_pedido, r.grau, r.resultado_global, entra, motivo))
            cont["casos"] += 1

            if cap is not None:
                con.execute("INSERT OR REPLACE INTO capitulos "
                            "(doc_id, caso_id, tema, titulo, texto, na_amostra) "
                            "VALUES (?,?,?,?,?,0)",
                            (doc_id, caso_id, tema, cap.titulo, cap.texto))

            gravar_valor(con, caso_id, "resultado_pedido", r.resultado_pedido,
                         r.trecho, "regra", VERSAO_REGRA)
            gravar_valor(con, caso_id, "resultado_global", r.resultado_global,
                         r.trecho, "regra", VERSAO_REGRA)
            gravar_valor(con, caso_id, "tipo_evento", evento, "", "regra", VERSAO_REGRA)
            if r.grau:
                gravar_valor(con, caso_id, "grau_deferido", str(r.grau),
                             r.trecho, "regra", VERSAO_REGRA)

    con.commit()
    relatorio(cont, estrategias, resultados, eventos)
    con.close()


def relatorio(cont, estrategias, resultados, eventos=None):
    print("=" * 68)
    print("PROCESSAMENTO")
    print("=" * 68)
    print(f"  documentos lidos          {cont['docs']:>6}")
    print(f"  sem dispositivo localizado{cont['sem_secao']:>6}")
    print(f"  sem capitulo do tema      {cont['sem_capitulo']:>6}  "
          f"(nao impede o rotulo)")
    print(f"  tema ausente do documento {cont['sem_mencao']:>6}")
    print(f"  casos gravados            {cont['casos']:>6}")
    print(f"  metadados do manifest     {cont['via_manifest']:>6}")
    if cont["via_regex"]:
        print(f"  metadados por regex       {cont['via_regex']:>6}  "
              f"<- nao estavam no manifest")

    print("\n  estrategia de corte")
    for k, v in sorted(estrategias.items(), key=lambda x: -x[1]):
        print(f"    {k:<24}{v:>6}  {v/max(cont['docs'],1):>6.0%}")
    falhou = estrategias.get("nao_encontrado", 0) / max(cont["docs"], 1)
    if falhou > 0.10:
        print(f"    >> {falhou:.0%} sem ancora: adicione padroes antes de escalar")

    if eventos:
        print("\n  tipo de evento processual")
        for k, v in sorted(eventos.items(), key=lambda x: -x[1]):
            print(f"    {k:<24}{v:>6}  {v/max(cont['docs'],1):>6.0%}")
        merito = eventos.get("MERITO_PRIMEIRO_GRAU", 0)
        print(f"    >> so MERITO_PRIMEIRO_GRAU entra na populacao "
              f"({merito/max(cont['docs'],1):.0%} do corpus)")

    print("\n  resultado do pedido")
    for k, v in sorted(resultados.items(), key=lambda x: -x[1]):
        print(f"    {k:<24}{v:>6}  {v/max(cont['casos'],1):>6.0%}")
    amb = resultados.get("ambiguo", 0) / max(cont["casos"], 1)
    print(f"\n  taxa de ambiguidade: {amb:.0%}", end="")
    print("   (alta: revise as regras)" if amb > 0.15 else "   (aceitavel)")
    print("\n  Proximo passo: gold_set.py amostrar")


# ------------------------------------------------------------------ demo
MODELO = """PODER JUDICIARIO
JUSTICA DO TRABALHO
TRIBUNAL REGIONAL DO TRABALHO DA 16a REGIAO
{vara}
ATOrd {cnj}

SENTENCA

I - RELATORIO
Reclamacao trabalhista postulando adicional de insalubridade.

II - FUNDAMENTACAO

II.1 - DA PRESCRICAO
Pronuncio a prescricao quinquenal das parcelas anteriores.

II.2 - DO ADICIONAL DE INSALUBRIDADE
{fundamentacao}

III - DISPOSITIVO
{dispositivo} Sentenca proferida em {data}.
"""

CENARIOS = [
    ("O laudo pericial concluiu pela insalubridade em grau medio.",
     "Ante o exposto, julgo PROCEDENTES EM PARTE os pedidos para condenar a "
     "reclamada ao pagamento do adicional de insalubridade em grau medio (20%)."),
    ("O perito concluiu pela inexistencia de agente insalubre.",
     "Ante o exposto, julgo IMPROCEDENTES os pedidos; indefiro o adicional de "
     "insalubridade."),
    ("Comprovada a entrega e fiscalizacao de EPI eficaz a partir de 2019.",
     "Isto posto, julgo PROCEDENTE EM PARTE; defiro as horas extras; indefiro o "
     "adicional de insalubridade."),
    ("O laudo apontou exposicao a agentes quimicos em grau maximo.",
     "Ante o exposto, julgo PROCEDENTE o pedido e condeno a reclamada ao "
     "pagamento do adicional de insalubridade em grau maximo."),
]


def demo(destino="../data/demo_raw"):
    import random
    random.seed(3)
    Path(destino).mkdir(parents=True, exist_ok=True)
    varas = ["1a VARA DO TRABALHO DE BALSAS", "2a VARA DO TRABALHO DE BALSAS",
             "1a VARA DO TRABALHO DE IMPERATRIZ"]
    for i in range(40):
        fund, disp = CENARIOS[i % len(CENARIOS)]
        txt = MODELO.format(
            vara=random.choice(varas),
            cnj=f"{i:07d}-45.2022.5.16.0002",
            fundamentacao=fund, dispositivo=disp,
            data=f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/2023")
        Path(destino, f"sent_{i:04d}.txt").write_text(txt, encoding="utf-8")
    print(f"40 sentencas falsas em {destino}\n")
    return destino


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="../data/normalized")
    ap.add_argument("--banco", default="../data/juripredict.db")
    ap.add_argument("--schema", default="schema.sql")
    ap.add_argument("--manifest", default="../data/manifests/falcao.sqlite",
                    help="manifest do coletor; fonte dos metadados")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    entrada = demo() if a.demo else a.entrada
    processar(entrada, a.banco, a.schema, a.manifest)