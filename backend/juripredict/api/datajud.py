"""Cliente da API pública do DataJud (CNJ) para ler os movimentos de um processo.

Só stdlib: é uma consulta por processo, sem necessidade de uma biblioteca HTTP.
O CNJ do processo já diz qual é o tribunal (campos J e TR), então não há o que
configurar por escritório. Cobre a Justiça do Trabalho (TRTs, J=5) e a Federal
(TRFs, J=4); os demais tribunais ficam fora até haver demanda.
"""

import json
import re
from datetime import timezone as dt_timezone
from http.client import HTTPException
from urllib import request

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

URL = "https://api-publica.datajud.cnj.jus.br/api_publica_{alias}/_search"
UTC = dt_timezone.utc
PREFIXO_POR_RAMO = {"5": "trt", "4": "trf"}


class DatajudErro(Exception):
    """Falha que a pessoa pode entender. ``http_status`` é o que a API devolve."""

    http_status = 502


class TribunalNaoSuportado(DatajudErro):
    http_status = 400


class DatajudNaoConfigurado(DatajudErro):
    http_status = 503


def apenas_digitos(numero):
    return re.sub(r"\D", "", numero or "")


def alias_do_tribunal(numero_cnj):
    """``0001234-56.2023.5.16.0001`` -> ``trt16``."""
    digitos = apenas_digitos(numero_cnj)
    prefixo = PREFIXO_POR_RAMO.get(digitos[13:14]) if len(digitos) == 20 else None
    if not prefixo or not int(digitos[14:16]):
        raise TribunalNaoSuportado(
            "Só é possível acompanhar processos da Justiça do Trabalho e da Justiça Federal."
        )
    return f"{prefixo}{int(digitos[14:16])}"


def _data_hora(valor):
    try:
        momento = parse_datetime(valor or "")
    except ValueError:  # formato certo, data impossível (ex.: dia 31 de fevereiro)
        return None
    if momento is None:
        return None
    return momento.replace(tzinfo=UTC) if timezone.is_naive(momento) else momento


def _complemento(movimento):
    partes = [
        f"{c.get('nome', '').strip()}: {c.get('descricao', '').strip()}".strip(": ")
        for c in movimento.get("complementosTabelados") or []
    ]
    return "; ".join(p for p in partes if p)


def _movimentos(resposta):
    movimentos = []
    for hit in (resposta.get("hits") or {}).get("hits") or []:
        for item in (hit.get("_source") or {}).get("movimentos") or []:
            data_hora = _data_hora(item.get("dataHora"))
            if data_hora is None or not item.get("nome"):
                continue
            movimentos.append(
                {
                    "data_hora": data_hora,
                    "codigo": item.get("codigo"),
                    "nome": str(item["nome"])[:255],
                    "complemento": _complemento(item),
                }
            )
    return movimentos


def consultar_movimentos(numero_cnj, *, abrir=request.urlopen):
    """Movimentos do processo (todos os graus), ou ``[]`` se o DataJud não o conhece.

    ``abrir`` é injetável: o teste troca a rede por uma resposta pronta.
    """
    alias = alias_do_tribunal(numero_cnj)
    chave = settings.DATAJUD_API_KEY.strip()
    if not chave:
        raise DatajudNaoConfigurado("A consulta ao DataJud não está configurada neste ambiente.")
    if not chave.lower().startswith("apikey "):
        chave = f"APIKey {chave}"

    corpo = {"query": {"match": {"numeroProcesso": apenas_digitos(numero_cnj)}}, "size": 10}
    requisicao = request.Request(
        URL.format(alias=alias),
        data=json.dumps(corpo).encode(),
        headers={"Authorization": chave, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with abrir(requisicao, timeout=30) as resposta:
            return _movimentos(json.loads(resposta.read().decode()))
    except (OSError, HTTPException, ValueError) as exc:
        # OSError cobre URLError, HTTPError e timeout; HTTPException, a conexão que cai no meio
        # da leitura. Sem repassar a mensagem: pode trazer a URL e a chave.
        raise DatajudErro("O DataJud não respondeu. Tente novamente mais tarde.") from exc
