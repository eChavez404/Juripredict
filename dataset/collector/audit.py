"""Auditoria da coleta: duplicidade, integridade e composicao do corpus.

O relatorio aqui e o que decide se vale aumentar a coleta. O piloto de 50
documentos existe para produzir estes numeros, nao para ter 50 documentos.
"""

import sqlite3
from collections import Counter
from typing import Iterable

from .models import Documento


def auditar_lote(documentos: Iterable[Documento]) -> dict:
    """Duplicidade e composicao do que acabou de ser baixado."""
    docs = list(documentos)
    ids = [d.id_sentenca for d in docs]
    cnjs = [d.numero_cnj for d in docs if d.numero_cnj]

    rep_id = {k: v for k, v in Counter(ids).items() if v > 1}
    rep_cnj = {k: v for k, v in Counter(cnjs).items() if v > 1}

    # invariante do enunciado: unicos nunca excede baixados
    assert len(set(ids)) <= len(ids), "contagem de unicos inconsistente"

    return {
        "baixados": len(docs),
        "ids_unicos": len(set(ids)),
        "duplicatas_id": rep_id,
        "cnjs_unicos": len(set(cnjs)),
        "cnjs_com_varios_documentos": rep_cnj,
        "tipos": Counter(d.tipo_documento for d in docs),
        "classes": Counter(d.classe_por_extenso for d in docs),
        "orgaos": Counter(d.orgao_por_extenso for d in docs),
        "sem_texto": sum(1 for d in docs if not d.texto_sentenca),
    }


def imprimir_auditoria(relatorio: dict, quantidade_total: int = 0) -> None:
    print("\n" + "=" * 68)
    print("AUDITORIA DO LOTE")
    print("=" * 68)

    if quantidade_total:
        print(f" Total informado pelo FALCAO : {quantidade_total}")
        print(" (documentos que casam com a busca textual — NAO e o numero")
        print(" de processos, nem o tamanho do futuro dataset)")

    print(f"\n  Documentos recebidos        : {relatorio['baixados']}")
    print(f"  idSentenca unicos           : {relatorio['ids_unicos']}")
    print(f"  Duplicatas de idSentenca    : {len(relatorio['duplicatas_id'])}")
    print(f"  CNJs unicos                 : {relatorio['cnjs_unicos']}")
    print(f"  CNJs com mais de um doc     : "
          f"{len(relatorio['cnjs_com_varios_documentos'])}")
    print(f"  Documentos sem textoSentenca: {relatorio['sem_texto']}")

    if relatorio["duplicatas_id"]:
        print("\n  ATENCAO: o mesmo idSentenca veio em mais de uma pagina.")
        print("  A busca ordena por score, entao a ordem pode variar entre")
        print("  requisicoes. A deduplicacao por idSentenca ja tratou disso.")
        for k, v in list(relatorio["duplicatas_id"].items())[:5]:
            print(f"    {k}: {v}x")

    print("\n  tipoDocumento")
    for tipo, n in relatorio["tipos"].most_common():
        print(f"    {str(tipo):<34}{n:>5}")
    print("  >> 'Sentenca' aqui inclui liquidacao e embargos. NAO usar este")
    print("     campo como criterio de merito.")

    print("\n  classe processual")
    for classe, n in relatorio["classes"].most_common(8):
        print(f"    {str(classe)[:33]:<34}{n:>5}")

    print("\n  orgao julgador")
    for orgao, n in relatorio["orgaos"].most_common(10):
        print(f"    {str(orgao)[:33]:<34}{n:>5}")


def auditar_manifest(caminho_sqlite: str) -> dict:
    """Integridade do manifest acumulado, entre execucoes."""
    con = sqlite3.connect(caminho_sqlite)
    q = lambda s: con.execute(s).fetchone()[0]
    rel = {
        "documentos": q("SELECT COUNT(*) FROM documentos"),
        "ids_unicos": q("SELECT COUNT(DISTINCT id_sentenca) FROM documentos"),
        "cnjs_unicos": q("SELECT COUNT(DISTINCT numero_cnj) FROM documentos"),
        "paginas": q("SELECT COUNT(*) FROM paginas"),
        "sem_hash": q("SELECT COUNT(*) FROM documentos "
                      "WHERE sha256_raw_document IS NULL OR sha256_raw_document=''"),
    }
    rel["cnjs_multi"] = con.execute(
        "SELECT COUNT(*) FROM (SELECT numero_cnj FROM documentos "
        "WHERE numero_cnj IS NOT NULL GROUP BY numero_cnj HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    con.close()

    assert rel["documentos"] == rel["ids_unicos"], \
        "manifest com id_sentenca duplicado — o UNIQUE falhou"
    return rel