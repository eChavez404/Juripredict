"""Comunicacao HTTP com o FALCAO.

Responsabilidades: montar a URL, respeitar intervalo entre requisicoes, repetir
em erro transitorio e traduzir as mensagens de erro do backend em excecoes.

Fatos empiricos que viram regra aqui:

  - size=10 funciona; size=20 e size=100 sao recusados com
    "Seu usuario nao tem autorizacao para realizar pesquisas com paginas de
    tamanho N". Por isso PAGE_SIZE_MAX = 10, e pedir mais levanta erro antes de
    sair da maquina;
  - sem `sessionId` o backend responde "Tentativa invalida de acesso ao
    sistema";
  - a paginacao e zero-based.
"""

import logging
import random
import time
from typing import Optional
import requests

from .models import Consulta, ErroFalcao, ErroSessao, Pagina

log = logging.getLogger(__name__)

BASE = "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/api/no-auth"
URL_PESQUISA = f"{BASE}/pesquisa"
URL_FILTROS = f"{BASE}/pesquisa/filtros"

PAGE_SIZE_MAX = 10          # limite imposto pelo servidor, verificado
PAUSA_MIN, PAUSA_MAX = 1.5, 3.0
TENTATIVAS = 4
STATUS_TRANSITORIOS = {429, 500, 502, 503, 504}

MARCAS_SESSAO = ("tentativa inv", "sess")


class ClienteFalcao:
    def __init__(self, sessao: requests.Session, session_id: str, pausa_min: float = PAUSA_MIN, pausa_max: float = PAUSA_MAX, timeout: int = 60):
        self.sessao = sessao
        self.session_id = session_id
        self.pausa_min = pausa_min
        self.pausa_max = pausa_max
        self.timeout = timeout
        self._ultima = 0.0

    def _respeitar_intervalo(self) -> None:
        espera = random.uniform(self.pausa_min, self.pausa_max)
        decorrido = time.monotonic() - self._ultima
        if decorrido < espera:
            time.sleep(espera - decorrido)
        self._ultima = time.monotonic()

    def _checar_erro_de_negocio(self, corpo) -> None:
        """O backend devolve 200 com {'userMessage': ...} em varios erros."""
        if not isinstance(corpo, dict):
            return
        msg = corpo.get("userMessage")
        if not msg:
            return
        baixa = msg.lower()
        if any(m in baixa for m in MARCAS_SESSAO):
            raise ErroSessao(msg, corpo)
        raise ErroFalcao(msg, corpo)

    def _get(self, url: str, params: dict) -> dict:
        for tentativa in range(1, TENTATIVAS + 1):
            self._respeitar_intervalo()
            try:
                r = self.sessao.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                if tentativa == TENTATIVAS:
                    raise
                espera = 2 ** tentativa + random.random()
                log.warning("rede falhou (%s); nova tentativa em %.1fs", e, espera)
                time.sleep(espera)
                continue

            if r.status_code in STATUS_TRANSITORIOS:
                if tentativa == TENTATIVAS:
                    raise ErroFalcao(f"HTTP {r.status_code} apos {TENTATIVAS} tentativas. " "Pare e verifique se houve bloqueio antes de insistir.")
                espera = 2 ** tentativa + random.random()
                log.warning("HTTP %s; nova tentativa em %.1fs", r.status_code, espera)
                time.sleep(espera)
                continue

            if r.status_code != 200:
                raise ErroFalcao(f"HTTP {r.status_code}: {r.text[:300]}")

            try:
                corpo = r.json()
            except ValueError:
                raise ErroFalcao(f"resposta nao e JSON: {r.text[:300]}")

            self._checar_erro_de_negocio(corpo)
            return corpo

        raise ErroFalcao("tentativas esgotadas")

    # ------------------------------------------------------------ publico
    def buscar_pagina(self, consulta: Consulta, page: int, size: int = PAGE_SIZE_MAX) -> Pagina:
        """Uma pagina da pesquisa. `page` e zero-based."""
        if page < 0:
            raise ValueError("page e zero-based; nao aceita negativo")
        if size > PAGE_SIZE_MAX:
            raise ValueError( f"size={size} e recusado pelo servidor. " f"O maximo verificado e {PAGE_SIZE_MAX}.")

        corpo = self._get(URL_PESQUISA, consulta.params(self.session_id, page, size))
        return Pagina.de_json(page, corpo)

    def buscar_filtros(self, consulta: Consulta) -> dict:
        """Agregacoes da pesquisa. Nao e necessario para paginar; serve para
        auditoria de cobertura por orgao julgador e classe."""
        params = consulta.params(self.session_id, page=0, size=PAGE_SIZE_MAX)
        params.pop("page")
        params.pop("size")
        return self._get(URL_FILTROS, params)