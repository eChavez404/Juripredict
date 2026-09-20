"""
Resolve os casos que a regra deixou em 'ambiguo', por leitura assistida.

    python rotular_ambiguos.py exportar            # gera a planilha de revisao
    python rotular_ambiguos.py importar            # grava os rotulos preenchidos
    python rotular_ambiguos.py conferir            # o que mudou, antes de gravar
    python rotular_ambiguos.py --demo              # sem banco, so o caminho de codigo

Por que existe um script separado do gold_set.py: sao papeis diferentes e
misturar os dois destroi a unica medida de erro que o projeto tem.

    gold_set.py          anotacao HUMANA, cega ao rotulo automatico.
                         E a referencia contra a qual tudo e medido.
    rotular_ambiguos.py  anotacao por MODELO sobre os casos que a regra
                         recusou. Aumenta a cobertura; nao mede nada.

Tudo que este script grava vai para `valores` com metodo='llm' e versao
propria (invariante I7), e a coluna canonica `casos.resultado_pedido` so e
sobrescrita onde ela valia 'ambiguo'. Nenhum rotulo de regra e alterado.

ATENCAO METODOLOGICA: os casos ambiguos nao sao uma amostra aleatoria - sao os
dificeis. Rotula-los por um processo diferente do resto do dataset introduz
erro de medicao que pode depender do desfecho. E por isso que o gold set
precisa amostrar TAMBEM entre os casos resolvidos aqui: sem isso nao ha como
saber se esta rotulagem e tao boa quanto a da regra.
"""

import argparse
import csv
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from cortar_secoes import cortar
from rotular_por_regra import TEMAS

VERSAO = "llm-ambiguos-v1"

ROTULOS_VALIDOS = {"deferido", "indeferido", "prescrito_total", "prejudicado",
                   "nao_analisado", "nao_mencionado", "ambiguo"}

COLUNAS = ["caso_id", "numero_cnj", "orgao_julgador", "data_sentenca",
           "rotulo_regra", "motivo_ambiguidade",
           "rotulo", "grau", "evidencia", "confianca", "observacao"]

# quanto texto da fundamentacao acompanha cada mencao ao tema
JANELA = 700


def _trechos_do_tema(texto, padrao, janela=JANELA, maximo=4):
    """
    Recortes em volta das mencoes ao tema, sem despejar a sentenca toda.

    Prioriza a ULTIMA mencao: e onde o capitulo fecha, e o fecho e que decide
    ("Pelo exposto, indefiro o adicional"). Pegar as primeiras mencoes traz a
    transcricao do pedido e o resumo do laudo, que nao decidem nada.
    """
    texto = texto or ""
    marcas = [(m.start(), m.end()) for m in padrao.finditer(texto)]
    if not marcas:
        return []

    escolhidas = marcas[-maximo:] if len(marcas) > maximo else marcas
    janelas = []
    for ini, fim in escolhidas:
        a = max(0, ini - janela // 3)
        b = min(len(texto), fim + janela)          # mais depois que antes
        if janelas and a <= janelas[-1][1]:
            janelas[-1] = (janelas[-1][0], b)      # funde recortes vizinhos
        else:
            janelas.append((a, b))
    return [texto[a:b].strip() for a, b in janelas]


# ------------------------------------------------------------------ exportar
def exportar(banco, saida, tema, limite):
    import re
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    linhas = con.execute("""
        SELECT c.caso_id, c.numero_cnj, c.resultado_pedido,
               d.orgao_julgador, d.data_sentenca, d.arquivo_bruto,
               v.evidencia AS motivo
        FROM casos c
        JOIN documentos d ON d.doc_id = c.doc_id
        LEFT JOIN valores v ON v.caso_id = c.caso_id
                           AND v.campo = 'resultado_pedido' AND v.metodo = 'regra'
        WHERE c.pedido = ? AND c.resultado_pedido = 'ambiguo'
        ORDER BY d.data_sentenca
        LIMIT ?
    """, (tema, limite)).fetchall()
    con.close()

    if not linhas:
        sys.exit("nenhum caso ambiguo no banco.")

    padrao = re.compile(TEMAS[tema], re.IGNORECASE)
    os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)

    lidos, sem_arquivo = 0, 0
    with open(saida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUNAS + ["dispositivo", "fundamentacao"])
        for l in linhas:
            caminho = Path(l["arquivo_bruto"] or "")
            if not caminho.exists():
                sem_arquivo += 1
                continue
            s = cortar(caminho.read_text(encoding="utf-8", errors="replace"))
            disp = " ¶ ".join(_trechos_do_tema(s.dispositivo, padrao)) \
                   or (s.dispositivo or "")[:2200]
            fund = " ¶ ".join(_trechos_do_tema(s.fundamentacao, padrao))
            w.writerow([l["caso_id"], l["numero_cnj"], l["orgao_julgador"],
                        l["data_sentenca"], l["resultado_pedido"],
                        (l["motivo"] or "")[:120],
                        "", "", "", "", ""] + [disp, fund])
            lidos += 1

    print(f"{lidos} casos em {saida}")
    if sem_arquivo:
        print(f"{sem_arquivo} sem arquivo bruto no caminho gravado - fora da planilha")
    print("\nPreencha as colunas `rotulo`, `grau`, `evidencia` e `confianca`.")
    print(f"rotulo   : {' | '.join(sorted(ROTULOS_VALIDOS))}")
    print("grau     : 10 | 20 | 40 | vazio")
    print("evidencia: o trecho que decidiu - e o que permite auditar depois")
    print("confianca: alta | media | baixa  (baixa nao entra no dataset)")


# ------------------------------------------------------------------ importar
def ler_planilha(arquivo):
    with open(arquivo, encoding="utf-8") as f:
        linhas = [l for l in csv.DictReader(f) if (l.get("rotulo") or "").strip()]

    erros, ok = [], []
    for i, l in enumerate(linhas, 2):
        rotulo = l["rotulo"].strip()
        if rotulo not in ROTULOS_VALIDOS:
            erros.append(f"linha {i}: rotulo '{rotulo}' invalido")
            continue
        grau = (l.get("grau") or "").strip()
        if grau and grau not in ("10", "20", "40"):
            erros.append(f"linha {i}: grau '{grau}' invalido")
            continue
        if rotulo == "deferido" and not grau:
            pass    # grau ausente e legitimo: nem toda sentenca o especifica
        if not (l.get("evidencia") or "").strip():
            erros.append(f"linha {i}: sem evidencia - I7 exige o trecho")
            continue
        ok.append(l)
    return ok, erros


def importar(banco, arquivo, confianca_minima, aplicar):
    linhas, erros = ler_planilha(arquivo)
    if erros:
        print("PLANILHA COM PROBLEMA:")
        for e in erros[:20]:
            print(f"  {e}")
        if len(erros) > 20:
            print(f"  ... e mais {len(erros) - 20}")
        sys.exit(1)

    ordem = {"alta": 3, "media": 2, "baixa": 1, "": 2}
    piso = ordem[confianca_minima]
    entram = [l for l in linhas if ordem.get((l.get("confianca") or "").strip(), 2) >= piso]
    fora = len(linhas) - len(entram)

    con = sqlite3.connect(banco)
    agora = datetime.now().isoformat(timespec="seconds")
    mudancas = {}
    for l in entram:
        caso_id, rotulo = l["caso_id"], l["rotulo"].strip()
        atual = con.execute("SELECT resultado_pedido FROM casos WHERE caso_id=?",
                            (caso_id,)).fetchone()
        if not atual:
            continue
        mudancas[f"{atual[0]} -> {rotulo}"] = mudancas.get(f"{atual[0]} -> {rotulo}", 0) + 1
        if not aplicar:
            continue

        # trilha de proveniencia: sempre gravada, mesmo quando nao sobrescreve
        con.execute(
            "INSERT OR REPLACE INTO valores "
            "(caso_id, campo, valor, evidencia, metodo, versao, extraido_em) "
            "VALUES (?,?,?,?,?,?,?)",
            (caso_id, "resultado_pedido", rotulo,
             (l.get("evidencia") or "")[:400], "llm", VERSAO, agora))
        grau = (l.get("grau") or "").strip()
        if grau:
            con.execute(
                "INSERT OR REPLACE INTO valores "
                "(caso_id, campo, valor, evidencia, metodo, versao, extraido_em) "
                "VALUES (?,?,?,?,?,?,?)",
                (caso_id, "grau_deferido", grau,
                 (l.get("evidencia") or "")[:400], "llm", VERSAO, agora))

        # a coluna canonica so muda onde a regra se declarou incapaz
        if atual[0] == "ambiguo":
            # I1: resolver a ambiguidade NAO transforma embargos ou liquidacao
            # em sentenca de merito de 1o grau. A primeira versao deste script
            # sobrescrevia motivo_exclusao com o rotulo novo e deixava 3 casos
            # nao-merito entrarem no dataset. O evento continua mandando.
            evento = con.execute(
                "SELECT valor FROM valores WHERE caso_id=? AND campo='tipo_evento'",
                (caso_id,)).fetchone()
            evento = evento[0] if evento else "MERITO_PRIMEIRO_GRAU"
            de_merito = evento == "MERITO_PRIMEIRO_GRAU"

            entra = 1 if (rotulo in ("deferido", "indeferido") and de_merito) else 0
            motivo = None if entra else (rotulo if de_merito else evento)
            con.execute(
                "UPDATE casos SET resultado_pedido=?, grau_deferido=?, "
                "entra_no_modelo=?, motivo_exclusao=? WHERE caso_id=?",
                (rotulo, int(grau) if grau else None, entra, motivo, caso_id))
    if aplicar:
        con.commit()
    con.close()

    print("=" * 68)
    print("IMPORTACAO DE ROTULOS" + ("" if aplicar else "  (SIMULACAO)"))
    print("=" * 68)
    print(f"  linhas preenchidas      {len(linhas):>6}")
    print(f"  fora por confianca      {fora:>6}  (piso: {confianca_minima})")
    print(f"  aplicadas               {len(entram):>6}")
    print("\n  transicoes")
    for k, n in sorted(mudancas.items(), key=lambda x: -x[1]):
        print(f"    {k:<34}{n:>5}")
    print(f"\n  metodo='llm'  versao='{VERSAO}'")
    if not aplicar:
        print("\n  nada foi gravado. Repita com --aplicar.")
    else:
        print("\n  Proximo passo: montar_dataset.py")
        print("  E amostre o gold set TAMBEM entre estes casos - sem isso nao ha")
        print("  como saber se esta rotulagem e tao boa quanto a da regra.")


# ------------------------------------------------------------------ conferir
def conferir(banco, tema):
    con = sqlite3.connect(banco)
    con.row_factory = sqlite3.Row
    print("=" * 68)
    print("COMPOSICAO ATUAL DO ROTULO")
    print("=" * 68)
    q = """SELECT c.resultado_pedido, COALESCE(v.metodo,'regra') metodo, COUNT(*) n
           FROM casos c
           LEFT JOIN valores v ON v.caso_id=c.caso_id
                AND v.campo='resultado_pedido' AND v.metodo='llm'
           WHERE c.pedido=? GROUP BY 1,2 ORDER BY 3 DESC"""
    for r in con.execute(q, (tema,)):
        print(f"  {r[0]:<20}{r[1]:<8}{r[2]:>6}")
    con.close()


# ===========================================================================
def demo(caminho="../data/demo_ambiguos.db"):
    """Banco falso com casos ambiguos, para exercitar exportar/importar."""
    os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
    if Path(caminho).exists():
        Path(caminho).unlink()
    con = sqlite3.connect(caminho)
    con.executescript(Path("schema.sql").read_text(encoding="utf-8"))
    destino = Path("../data/demo_ambiguos_raw")
    destino.mkdir(parents=True, exist_ok=True)
    for i in range(6):
        txt = (f"PODER JUDICIARIO\n\nII - FUNDAMENTACAO\n\n"
               f"DO ADICIONAL DE INSALUBRIDADE\nO laudo pericial apontou "
               f"exposicao a agente biologico no periodo.\n\n"
               f"III - DISPOSITIVO\nAnte o exposto, julgo PARCIALMENTE "
               f"PROCEDENTES os pedidos. Custas pela reclamada.\n")
        arq = destino / f"amb_{i:03d}.txt"
        arq.write_text(txt, encoding="utf-8")
        con.execute("INSERT INTO documentos (doc_id, numero_cnj, orgao_julgador,"
                    " data_sentenca, tipo_decisao, julga_insalubridade,"
                    " arquivo_bruto, sha256, fonte) VALUES (?,?,?,?,?,?,?,?,?)",
                    (f"d{i}", f"{i:07d}-45.2024.5.16.0002", "1a VT Balsas",
                     f"2024-0{i+1}-10", "sentenca_merito", "sim", str(arq), "", "demo"))
        con.execute("INSERT INTO casos (caso_id, numero_cnj, pedido, doc_id,"
                    " resultado_pedido, entra_no_modelo, motivo_exclusao)"
                    " VALUES (?,?,?,?,?,0,'ambiguo')",
                    (f"c{i}", f"{i:07d}-45.2024.5.16.0002", "insalubridade",
                     f"d{i}", "ambiguo"))
        con.execute("INSERT INTO valores (caso_id, campo, valor, evidencia,"
                    " metodo, versao) VALUES (?,?,?,?,?,?)",
                    (f"c{i}", "resultado_pedido", "ambiguo",
                     "procedencia parcial sem nomear o pedido", "regra", "demo"))
    con.commit(); con.close()
    print(f"banco falso em {caminho}: 6 casos ambiguos\n")
    return caminho


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    e = sub.add_parser("exportar")
    e.add_argument("--banco", default="../data/juripredict.db")
    e.add_argument("--saida", default="../data/ambiguos_para_revisao.csv")
    e.add_argument("--tema", default="insalubridade")
    e.add_argument("--limite", type=int, default=1000)

    i = sub.add_parser("importar")
    i.add_argument("--banco", default="../data/juripredict.db")
    i.add_argument("--arquivo", default="../data/ambiguos_revisados.csv")
    i.add_argument("--confianca-minima", default="media",
                   choices=("alta", "media", "baixa"))
    i.add_argument("--aplicar", action="store_true",
                   help="sem isto, so simula e mostra as transicoes")

    c = sub.add_parser("conferir")
    c.add_argument("--banco", default="../data/juripredict.db")
    c.add_argument("--tema", default="insalubridade")

    a = ap.parse_args()

    if a.demo:
        banco = demo()
        exportar(banco, "../data/demo_ambiguos.csv", "insalubridade", 1000)
        sys.exit(0)

    if not a.cmd:
        ap.error("informe um subcomando: exportar | importar | conferir")
    if a.cmd == "exportar":
        exportar(a.banco, a.saida, a.tema, a.limite)
    elif a.cmd == "importar":
        importar(a.banco, a.arquivo, a.confianca_minima, a.aplicar)
    else:
        conferir(a.banco, a.tema)
