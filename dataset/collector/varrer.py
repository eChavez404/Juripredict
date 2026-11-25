"""Varredura de um periodo longo em janelas de data: `python -m collector.varrer`.

    python -m collector.varrer \
      --query "" --tribunal TRT16 --collection sentencas \
      --date-start 2018-01-01 --date-end 2026-11-15 \
      --data-dir C:/dados/falcao --session-id <valor>

`collector.falcao` baixa uma consulta de cada vez. Aqui o intervalo e fatiado
em meses, e o mes cujo total chega a `--limite` e dividido ao meio ate caber:
a paginacao do servidor nao passa de 200 resultados por busca, e o total
informado vem truncado em 10.000.

Os meses vao do mais recente ao mais antigo: o FALCAO tem cota diaria de
requisicoes, a coleta completa leva semanas, e o recente e o mais util.

Retomada: janela completa no manifest e pulada. Se a sessao expirar ou a cota
acabar, a varredura para; rode o mesmo comando depois.
"""

import argparse
import math
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta

from .client import ClienteFalcao, PAGE_SIZE_MAX
from .collector import coletar
from .models import Consulta, ErroFalcao, ErroLimite, ErroSessao
from .session import sessao_http
from .storage import Armazenamento

# Verificado em 2026-11-17: alem da pagina 20 (200 resultados com 10 por pagina) o FALCAO
# responde 403, "Seu usuario nao tem autorizacao para ir alem da pagina 20". A janela que
# chega a esse total e dividida ao meio ate caber.
LIMITE_PADRAO = 200


def meses(ini: date, fim: date):
    d = ini
    while d <= fim:
        ultimo = date(d.year, d.month, monthrange(d.year, d.month)[1])
        yield d, min(ultimo, fim)
        d = ultimo + timedelta(days=1)


def janelas(ini: date, fim: date, contar, limite: int) -> list:
    """Divide [ini, fim] ao meio ate o total de cada parte ficar abaixo do
    limite. Devolve [(ini, fim, total)]. Um dia que nao cabe volta como esta."""
    total = contar(ini, fim)
    if total < limite or ini == fim:
        return [(ini, fim, total)]
    meio = ini + (fim - ini) // 2
    return (janelas(ini, meio, contar, limite)
            + janelas(meio + timedelta(days=1), fim, contar, limite))


def concluida(armazenamento: Armazenamento, consulta: Consulta) -> bool:
    total, gravadas = armazenamento.con.execute(
        "SELECT MAX(quantidade_total), COUNT(*) FROM paginas WHERE slug=?",
        (consulta.slug(),)).fetchone()
    return gravadas > 0 and gravadas >= math.ceil((total or 0) / PAGE_SIZE_MAX)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="collector.varrer", description="Varredura do FALCAO em janelas de data")
    p.add_argument("--query", required=True, help='texto da pesquisa; "" se o servidor aceitar pesquisa vazia')
    p.add_argument("--tribunal", default="TRT16")
    p.add_argument("--collection", default="sentencas")
    p.add_argument("--date-start", required=True, type=date.fromisoformat)
    p.add_argument("--date-end", default=date.today(), type=date.fromisoformat)
    p.add_argument("--limite", type=int, default=LIMITE_PADRAO, help="ultima posicao que a paginacao alcanca")
    p.add_argument("--session-id", default=None, help="sessao obtida no navegador")
    p.add_argument("--data-dir", required=True, help="fora do OneDrive: sao milhares de arquivos")
    a = p.parse_args(argv)

    try:
        sessao, session_id = sessao_http(a.session_id)
    except ErroSessao as e:
        print(f"\n{e}", file=sys.stderr)
        return 1

    cliente = ClienteFalcao(sessao, session_id)
    armazenamento = Armazenamento(a.data_dir)

    def consulta(ini, fim):
        return Consulta(a.query, a.tribunal, a.collection, ini.isoformat(), fim.isoformat())

    primeiras = {}  # a pagina 0 que contou a janela e reaproveitada na coleta

    def contar(ini, fim):
        primeiras[(ini, fim)] = cliente.buscar_pagina(consulta(ini, fim), 0)
        return primeiras[(ini, fim)].quantidade_total

    incompletas = []
    try:
        for m_ini, m_fim in reversed(list(meses(a.date_start, a.date_end))):
            if concluida(armazenamento, consulta(m_ini, m_fim)):
                continue
            for ini, fim, total in janelas(m_ini, m_fim, contar, a.limite):
                c = consulta(ini, fim)
                print(f"\n== {ini} a {fim}: {total} documentos")
                if total == 0:
                    # grava a página vazia: sem ela, a janela seria contada de novo a cada rodada
                    armazenamento.gravar_pagina(c, primeiras[(ini, fim)])
                    continue
                if concluida(armazenamento, c):
                    continue
                coletar(cliente, armazenamento, c, math.ceil(min(total, a.limite) / PAGE_SIZE_MAX),
                        primeira=primeiras.get((ini, fim)))
                if total >= a.limite or not concluida(armazenamento, c):
                    incompletas.append((ini, fim, total))
    except ErroLimite as e:
        libera = datetime.now() + timedelta(seconds=e.espera_s)
        n = armazenamento.contar()
        print(f"\nCota diaria do FALCAO esgotada; libera por volta de {libera:%d/%m %H:%M}. "
              f"Manifest: {n['documentos']} documentos. Rode o mesmo comando depois; "
              "o que ja foi baixado e pulado.", file=sys.stderr)
        return 3
    except ErroSessao:
        print("\nSessao expirou. Pegue outra no navegador e rode o mesmo comando "
              "com --session-id; o que ja foi baixado e pulado.", file=sys.stderr)
        return 1
    except ErroFalcao as e:
        print(f"\nFALCAO recusou: {e.mensagem_usuario}. Parando.", file=sys.stderr)
        return 1
    else:
        n = armazenamento.contar()
        print(f"\nManifest: {n['documentos']} documentos, {n['cnjs_unicos']} processos.")
        for ini, fim, total in incompletas:
            print(f"INCOMPLETA: {ini} a {fim} ({total} documentos)")
        return 2 if incompletas else 0
    finally:
        armazenamento.fechar()


if __name__ == "__main__":
    raise SystemExit(main())
