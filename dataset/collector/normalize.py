"""HTML -> texto limpo.

Regra inviolavel: o RAW nunca e alterado. Esta camada produz uma representacao
derivada, e so isso.

`textoSentenca` vem como HTML completo e pode carregar imagens embutidas em
base64, que inflam o JSON. A normalizacao remove script, style e as imagens,
e extrai o texto.
"""

import re
from typing import Optional

RE_SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
RE_IMG_BASE64 = re.compile(r"<img[^>]*src=[\"']data:[^\"']*[\"'][^>]*>", re.I)
RE_TAG = re.compile(r"<[^>]+>")
RE_ESPACO = re.compile(r"[ \t\u00a0]+")
RE_LINHAS = re.compile(r"\n{3,}")

ENTIDADES = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
    "&quot;": '"', "&#39;": "'", "&aacute;": "á", "&eacute;": "é",
    "&iacute;": "í", "&oacute;": "ó", "&uacute;": "ú", "&ccedil;": "ç",
    "&atilde;": "ã", "&otilde;": "õ", "&acirc;": "â", "&ecirc;": "ê",
    "&ocirc;": "ô", "&agrave;": "à",
}

QUEBRAM_LINHA = ("</p>", "</div>", "</tr>", "</li>", "</h1>", "</h2>",
                 "</h3>", "<br>", "<br/>", "<br />")


def contar_base64(html: str) -> int:
    return len(RE_IMG_BASE64.findall(html or ""))


def html_para_texto(html: Optional[str]) -> str:
    """Extrai texto. Usa BeautifulSoup se disponivel; senao, regex."""
    if not html:
        return ""

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return _sem_bs4(html)

    sopa = BeautifulSoup(html, "html.parser")
    for tag in sopa(["script", "style"]):
        tag.decompose()
    for img in sopa.find_all("img"):
        src = img.get("src") or ""
        if src.startswith("data:"):
            img.decompose()
    texto = sopa.get_text("\n")
    return _arrumar(texto)


def _sem_bs4(html: str) -> str:
    t = RE_SCRIPT_STYLE.sub(" ", html)
    t = RE_IMG_BASE64.sub(" ", t)
    for marca in QUEBRAM_LINHA:
        t = t.replace(marca, marca + "\n")
    t = RE_TAG.sub(" ", t)
    for ent, char in ENTIDADES.items():
        t = t.replace(ent, char)
    return _arrumar(t)


def _arrumar(texto: str) -> str:
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    texto = RE_ESPACO.sub(" ", texto)
    texto = "\n".join(l.strip() for l in texto.split("\n"))
    texto = RE_LINHAS.sub("\n\n", texto)
    return texto.strip()


def resumo_normalizacao(html: Optional[str]) -> dict:
    """Metricas da normalizacao, para o relatorio do piloto."""
    bruto = len(html or "")
    limpo = html_para_texto(html)
    return {
        "chars_html": bruto,
        "chars_texto": len(limpo),
        "imagens_base64": contar_base64(html or ""),
        "reducao": 0.0 if bruto == 0 else 1 - len(limpo) / bruto,
    }