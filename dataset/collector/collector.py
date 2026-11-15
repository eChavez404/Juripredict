"""Orquestracao da coleta: paginacao, retomada, deduplicacao e relatorio.

Nao classifica nada. Nao descarta documento que "parece irrelevante". O objetivo
desta camada e produzir um corpus RAW reproduzivel — a classificacao de evento
(merito, liquidacao, embargos, execucao) vem depois, sobre o corpus.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from .audit import auditar_lote, imprimir_auditoria
from .client import ClienteFalcao, PAGE_SIZE_MAX
from .models import Consulta, Documento, ErroFalcao, ErroLimite, ErroPagina, ErroSessao, Pagina
from .normalize import html_para_texto, resumo_normalizacao
from .storage import Armazenamento

log = logging.getLogger(__name__)


@dataclass
class Resultado:
    consulta: Consulta
    quantidade_total: int = 0
    paginas_baixadas: int = 0
    paginas_puladas: int = 0
    documentos: list = field(default_factory=list)
    documentos_novos: int = 0
    documentos_pulados: int = 0
    normalizacao: list = field(default_factory=list)


def coletar(cliente: ClienteFalcao, armazenamento: Armazenamento,
            consulta: Consulta, paginas: int,
            page_size: int = PAGE_SIZE_MAX, force: bool = False,
            normalizar: bool = True,
            primeira: Optional[Pagina] = None) -> Resultado:
    """
    Baixa `paginas` paginas, comecando em page=0 (a paginacao e zero-based).
    `primeira` e a pagina 0 ja obtida por quem chamou, para nao pedi-la de novo.

    Para antes se uma pagina vier vazia — e o sinal de fim de resultados.
    """
    res = Resultado(consulta=consulta)
    vistos: set = set()

    print(f"\nConsulta:\n  {consulta.tribunal}\n  {consulta.colecao}\n"
          f"  {consulta.texto}\n  {consulta.data_inicio} -> {consulta.data_fim}\n")

    for page in range(paginas):
        if not force and armazenamento.pagina_ja_baixada(consulta, page):
            log.info("pagina %s ja baixada e integra; pulando", page)
            res.paginas_puladas += 1
            continue

        try:
            if page == 0 and primeira is not None:
                pagina = primeira
            else:
                pagina = cliente.buscar_pagina(consulta, page, page_size)
        except ErroLimite:
            raise
        except ErroSessao as e:
            print(f"\nSessao invalida na pagina {page}: {e.mensagem_usuario}")
            print("Obtenha uma sessao nova no navegador e rode de novo com "
                  "--session-id. As paginas ja baixadas nao serao refeitas.")
            break
        except ErroPagina:
            pagina = None
        except ErroFalcao as e:
            print(f"\nFALCAO recusou a pagina {page}: {e.mensagem_usuario}")
            print("Parando. Nao insista automaticamente.")
            break

        if pagina is None:
            documentos = metades(cliente, consulta, page, page_size)
            print(f"Pagina {page}: o servidor falhou ao monta-la; "
                  f"{len(documentos)} de {page_size} recuperados em metades")
        else:
            if page == 0:
                res.quantidade_total = pagina.quantidade_total

            if pagina.vazia():
                print(f"Pagina {page}: vazia — fim dos resultados")
                break

            armazenamento.gravar_pagina(consulta, pagina, force=force)
            res.paginas_baixadas += 1
            documentos = pagina.documentos

        novos = 0
        for doc in documentos:
            res.documentos.append(doc)
            if doc.id_sentenca in vistos:
                continue
            vistos.add(doc.id_sentenca)

            if armazenamento.gravar_documento(consulta, doc, page, force=force):
                novos += 1
                res.documentos_novos += 1
                if normalizar and doc.texto_sentenca:
                    armazenamento.gravar_normalizado(
                        consulta, doc.id_sentenca,
                        html_para_texto(doc.texto_sentenca))
                    res.normalizacao.append(
                        resumo_normalizacao(doc.texto_sentenca))
            else:
                res.documentos_pulados += 1

        print(f"Pagina {page}: {len(documentos)} documentos "
              f"({novos} novos)")

    return res


def metades(cliente: ClienteFalcao, consulta: Consulta, page: int,
            page_size: int) -> list:
    """Refaz uma pagina que o servidor nao montou em duas de metade do
    tamanho. 5 e o menor tamanho aceito, entao um documento ruim custa no
    maximo 5. A pagina fica fora do manifest, e a janela segue incompleta."""
    if page_size % 2:
        return []
    docs = []
    for sub in (2 * page, 2 * page + 1):
        try:
            docs += cliente.buscar_pagina(consulta, sub, page_size // 2).documentos
        except ErroPagina:
            log.warning("pagina %s, metade %s: o servidor falhou de novo", page, sub)
    return docs


def relatorio_final(res: Resultado, armazenamento: Armazenamento) -> None:
    rel = auditar_lote(res.documentos)
    imprimir_auditoria(rel, res.quantidade_total)

    print("\n" + "-" * 68)
    print("ARMAZENAMENTO")
    print("-" * 68)
    print(f"  paginas baixadas : {res.paginas_baixadas}")
    print(f"  paginas puladas  : {res.paginas_puladas} (ja existiam)")
    print(f"  documentos novos : {res.documentos_novos}")
    print(f"  documentos pulados: {res.documentos_pulados} (ja no manifest)")

    if res.normalizacao:
        n = len(res.normalizacao)
        html = sum(x["chars_html"] for x in res.normalizacao)
        texto = sum(x["chars_texto"] for x in res.normalizacao)
        b64 = sum(x["imagens_base64"] for x in res.normalizacao)
        print(f"\n  HTML bruto       : {html/1e6:.1f} MB em {n} documentos")
        print(f"  texto extraido   : {texto/1e6:.1f} MB")
        print(f"  reducao          : {1 - texto/max(html,1):.0%}")
        print(f"  imagens base64   : {b64}")
        if b64:
            media = html / max(n, 1)
            print(f"\n  Projecao para {res.quantidade_total} documentos: "
                  f"~{media * res.quantidade_total / 1e9:.1f} GB de RAW.")
            print("  Confira o espaco em disco antes de ampliar a coleta.")

    print("\n  RAW salvo em:", armazenamento.dir_paginas)
    print("  Manifest     :", armazenamento.manifest)

    print("\n" + "-" * 68)
    print("PROXIMO PASSO")
    print("-" * 68)
    print("  Abrir alguns documentos de data/normalized/ e classificar a mao:")
    print("    MERITO_PRIMEIRO_GRAU | EMBARGOS_DECLARACAO | LIQUIDACAO")
    print("    EXECUCAO | OUTRO")
    print("  A proporcao de cada um decide se vale ampliar a coleta.")