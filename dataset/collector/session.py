"""Criacao e validacao da sessao publica do FALCAO.

O que foi observado empiricamente:

  - `sessionId` e obrigatorio na query; sem ele o backend responde
    "Tentativa invalida de acesso ao sistema";
  - na sessao do navegador existiam, ao mesmo tempo, `sessionId=_2761j7j` na
    URL e o cookie `SESSION_ID_COOKIE_PUJ=_2761j7j`;
  - havia tambem um `JSESSIONID`.

O que NAO foi observado: como a sessao e criada. Por isso o bootstrap aqui e
uma TENTATIVA documentada — visitar a pagina publica e ler os cookies — com
fallback explicito para o usuario informar uma sessao obtida no navegador.

Nao ha, e nao deve haver, nenhuma tentativa de contornar CAPTCHA, limite de
requisicoes ou autorizacao. Se o bootstrap falhar, o coletor para e explica.
"""

import logging
import re
from typing import Optional

import requests

from .models import ErroSessao

log = logging.getLogger(__name__)

PAGINA_PUBLICA = "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional/pesquisa"
COOKIE_SESSAO = "SESSION_ID_COOKIE_PUJ"
COOKIE_JSESSION = "JSESSIONID"

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

CABECALHOS = {
    "accept": "application/json, text/plain, */*",
    "referer": PAGINA_PUBLICA,
    "user-agent": USER_AGENT,
}

# O sessionId observado tinha a forma _2761j7j: underscore + alfanumericos.
PADRAO_SESSION_ID = re.compile(r"^_?[A-Za-z0-9_-]{4,64}$")


def mascarar(valor: Optional[str]) -> str:
    """Nunca logar sessao inteira. Mostra so o suficiente para depurar."""
    if not valor:
        return "<vazio>"
    if len(valor) <= 4:
        return "*" * len(valor)
    return f"{valor[:3]}...{valor[-2:]}"


def valido(session_id: Optional[str]) -> bool:
    return bool(session_id) and bool(PADRAO_SESSION_ID.match(session_id))


def bootstrap_session(sessao: requests.Session,
                      timeout: int = 30) -> Optional[str]:
    """
    Tenta obter um sessionId visitando a pagina publica e lendo os cookies.

    Retorna o sessionId se encontrar, ou None. Nao levanta excecao: falhar aqui
    e um resultado esperado, e o chamador decide usar o fallback manual.
    """
    sessao.headers.update({"user-agent": USER_AGENT})
    try:
        r = sessao.get(PAGINA_PUBLICA, timeout=timeout)
    except requests.RequestException as e:
        log.warning("bootstrap: falha ao abrir a pagina publica (%s)", e)
        return None

    log.info("bootstrap: HTTP %s na pagina publica", r.status_code)
    cookies = {c.name: c.value for c in sessao.cookies}
    log.info("bootstrap: cookies recebidos: %s", sorted(cookies))

    sid = cookies.get(COOKIE_SESSAO)
    if valido(sid):
        log.info("bootstrap: %s encontrado (%s)", COOKIE_SESSAO, mascarar(sid))
        return sid

    if COOKIE_JSESSION in cookies:
        log.info("bootstrap: so veio %s; ele NAO serve como sessionId da pesquisa",
                 COOKIE_JSESSION)

    log.warning("bootstrap: %s nao veio. Use --session-id com uma sessao do "
                "navegador.", COOKIE_SESSAO)
    return None


def obter_session_id(sessao: requests.Session,
                     manual: Optional[str] = None) -> str:
    """
    Resolve o sessionId: o informado manualmente tem precedencia; senao tenta o
    bootstrap. Levanta ErroSessao se nenhum caminho funcionar.
    """
    if manual:
        if not valido(manual):
            raise ErroSessao(
                f"sessionId informado tem formato inesperado: {mascarar(manual)}")
        log.info("sessao: usando sessionId informado (%s)", mascarar(manual))
        # o backend associa sessionId e cookie; manter os dois coerentes
        sessao.cookies.set(COOKIE_SESSAO, manual,
                           domain="jurisprudencia.jt.jus.br")
        return manual

    sid = bootstrap_session(sessao)
    if sid:
        return sid

    raise ErroSessao(
        "Nao foi possivel criar a sessao automaticamente.\n\n"
        "Como obter uma manualmente:\n"
        f"  1. abra {PAGINA_PUBLICA}\n"
        "  2. faca qualquer pesquisa\n"
        "  3. F12 > aba Network > clique na chamada 'pesquisa'\n"
        "  4. copie o valor de sessionId da query string\n"
        "  5. rode de novo com --session-id <valor>\n\n"
        "A sessao e temporaria e expira. Nunca versione esse valor no git."
    )


def sessao_http(session_id_manual: Optional[str] = None) -> tuple:
    """Devolve (requests.Session pronta, session_id)."""
    s = requests.Session()
    s.headers.update(CABECALHOS)
    return s, obter_session_id(s, session_id_manual)