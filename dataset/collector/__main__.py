"""CLI do coletor.

    python -m collector.falcao \
      --query "insalubridade" \
      --tribunal TRT16 \
      --collection sentencas \
      --date-start 2024-01-01 \
      --date-end 2026-08-18 \
      --pages 5 \
      --page-size 10
"""

import argparse
import logging
import sys

from .client import ClienteFalcao, PAGE_SIZE_MAX
from .collector import coletar, relatorio_final
from .models import Consulta, ErroSessao
from .session import sessao_http
from .storage import Armazenamento


def configurar_log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verboso else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="collector.falcao", description="Coletor do FALCAO / TRT")
    p.add_argument("--query", required=True, help="texto da pesquisa")
    p.add_argument("--tribunal", default="TRT16")
    p.add_argument("--collection", default="sentencas")
    p.add_argument("--date-start", required=True)
    p.add_argument("--date-end", required=True)
    p.add_argument("--pages", type=int, default=5, help="quantas paginas, a partir de page=0")
    p.add_argument("--page-size", type=int, default=PAGE_SIZE_MAX, help=f"o servidor recusa acima de {PAGE_SIZE_MAX}")
    p.add_argument("--session-id", default=None, help="sessao obtida no navegador; usar se o bootstrap falhar")
    p.add_argument("--data-dir", default="data")
    p.add_argument("--force", action="store_true", help="refaz downloads ja existentes")
    p.add_argument("--no-normalize", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)

    configurar_log(a.verbose)

    if a.page_size > PAGE_SIZE_MAX:
        print(f"page-size={a.page_size} e recusado pelo servidor "
              f"(maximo verificado: {PAGE_SIZE_MAX}).", file=sys.stderr)
        return 2

    try:
        sessao, session_id = sessao_http(a.session_id)
    except ErroSessao as e:
        print(f"\n{e}", file=sys.stderr)
        return 1

    print("Sessao publica criada: OK")

    consulta = Consulta(texto=a.query, tribunal=a.tribunal, colecao=a.collection, data_inicio=a.date_start, data_fim=a.date_end)
    cliente = ClienteFalcao(sessao, session_id)
    armazenamento = Armazenamento(a.data_dir)

    try:
        res = coletar(cliente, armazenamento, consulta, a.pages, a.page_size, a.force, not a.no_normalize)
        relatorio_final(res, armazenamento)
    finally:
        armazenamento.fechar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())