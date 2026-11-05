"""Jurimetria da carteira: recortes, rastreabilidade e exportação.

Toda taxa passa por ``taxa_com_contexto``: nenhuma sai sem o n e o intervalo, e abaixo do piso
sai nula com o motivo. Vale também para o arquivo exportado, que circula fora do sistema.
"""

import csv
import io

from django.db.models import Count
from rest_framework.exceptions import ValidationError

from .estatistica import taxa_com_contexto
from .models import Processo

RESULTADOS_CONCLUIDOS = ("FAVORAVEL", "ACORDO", "DESFAVORAVEL")
SEM_DATA = "sem_data"


def filtros_da_requisicao(parametros):
    """Valida ``area``, ``ano``, ``vara`` e ``resultado``. Filtro inválido é 400, nunca vazio mudo."""
    filtros = {}
    area = parametros.get("area")
    if area:
        if area not in dict(Processo.AREA_CHOICES):
            raise ValidationError({"area": ["Área inválida."]})
        filtros["area"] = area
    ano = parametros.get("ano")
    if ano and ano != SEM_DATA:
        if not (ano.isascii() and ano.isdigit() and 1900 <= int(ano) <= 2100):
            raise ValidationError({"ano": ["Informe um ano válido, ou sem_data."]})
        ano = int(ano)
    if ano:
        filtros["ano"] = ano
    resultado = parametros.get("resultado")
    if resultado:
        if resultado not in RESULTADOS_CONCLUIDOS:
            raise ValidationError({"resultado": ["Resultado inválido."]})
        filtros["resultado"] = resultado
    if parametros.get("vara"):
        filtros["vara"] = parametros["vara"]
    return filtros


def aplicar_filtros(processos, filtros):
    if "area" in filtros:
        processos = processos.filter(area=filtros["area"])
    if "vara" in filtros:
        processos = processos.filter(vara=filtros["vara"])
    if "resultado" in filtros:
        processos = processos.filter(resultado=filtros["resultado"])
    if filtros.get("ano") == SEM_DATA:
        processos = processos.filter(data_distribuicao__isnull=True)
    elif "ano" in filtros:
        processos = processos.filter(data_distribuicao__year=filtros["ano"])
    return processos


def concluidos(processos):
    return processos.exclude(resultado="PENDENTE")


def _contagens(analisados, campo):
    """``{grupo: {resultado: n}}`` numa consulta só; ``order_by()`` tira a ordenação do GROUP BY."""
    grupos = {}
    linhas = analisados.values(campo, "resultado").annotate(n=Count("id")).order_by()
    for linha in linhas:
        grupos.setdefault(linha[campo], {})[linha["resultado"]] = linha["n"]
    return grupos


def _taxa(contagem, piso):
    favoraveis = contagem.get("FAVORAVEL", 0) + contagem.get("ACORDO", 0)
    return taxa_com_contexto(favoraveis, sum(contagem.values()), piso=piso)


def _por_grupo(analisados, campo, piso):
    return {
        grupo: {"contagem": contagem, **_taxa(contagem, piso)}
        for grupo, contagem in _contagens(analisados, campo).items()
    }


def _sem_contagem(item):
    return {chave: valor for chave, valor in item.items() if chave != "contagem"}


def analisar(processos, *, piso):
    """Tudo o que a tela e a exportação mostram, para o recorte já filtrado."""
    analisados = concluidos(processos)
    contagem_geral = {
        item["resultado"]: item["n"]
        for item in analisados.values("resultado").annotate(n=Count("id")).order_by()
    }
    geral = _taxa(contagem_geral, piso)

    varas = sorted(
        (
            {"vara": vara, **item}
            for vara, item in _por_grupo(analisados, "vara", piso).items()
        ),
        key=lambda item: (-item["total"], item["vara"]),
    )
    anos = sorted(
        (
            {"ano": ano, **item}
            for ano, item in _por_grupo(analisados, "data_distribuicao__year", piso).items()
        ),
        # mais recentes primeiro; "sem data" por último
        key=lambda item: (item["ano"] is None, -(item["ano"] or 0)),
    )
    return {
        "geral": geral,
        "contagem_geral": contagem_geral,
        "por_vara": varas,
        "por_ano": anos,
    }


def resposta_publica(analise):
    return {
        "por_vara": [_sem_contagem(item) for item in analise["por_vara"]],
        "por_ano": [_sem_contagem(item) for item in analise["por_ano"]],
    }


def opcoes_de_filtro(processos):
    """Só o que existe nos concluídos da carteira: filtro que daria sempre vazio não aparece."""
    analisados = concluidos(processos)
    areas = dict(Processo.AREA_CHOICES)
    return {
        "areas": [
            {"valor": valor, "rotulo": areas.get(valor, valor)}
            for valor in sorted(analisados.values_list("area", flat=True).distinct().order_by())
        ],
        "anos": sorted(
            (
                data.year
                for data in analisados.exclude(data_distribuicao__isnull=True)
                .dates("data_distribuicao", "year")
                .order_by()
            ),
            reverse=True,
        ),
    }


def _celula_segura(valor):
    """Evita injeção de fórmula: planilha executaria uma vara cadastrada como ``=CMD(...)``."""
    texto = str(valor)
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _linha(recorte, grupo, item):
    contagem = item["contagem"]
    intervalo = item["intervalo_favoravel"] or {}
    return [
        recorte,
        _celula_segura(grupo),
        item["total"],
        contagem.get("FAVORAVEL", 0),
        contagem.get("ACORDO", 0),
        contagem.get("DESFAVORAVEL", 0),
        "" if item["favoravel"] is None else item["favoravel"],
        intervalo.get("min", ""),
        intervalo.get("max", ""),
        item["motivo"] or "",
    ]


def exportar_csv(analise, *, descricao_recorte):
    """CSV para Excel em português: separador ``;`` e BOM para os acentos abrirem certo."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Jurimetria da carteira", _celula_segura(descricao_recorte)])
    escritor.writerow(
        [
            "Taxa = favoráveis + acordos sobre os concluídos. IC de 95% (Wilson). "
            "Ano = ano de distribuição do processo."
        ]
    )
    escritor.writerow([])
    escritor.writerow(
        [
            "Recorte", "Grupo", "Processos concluídos", "Favoráveis", "Acordos", "Desfavoráveis",
            "Taxa (%)", "IC 95% mín. (%)", "IC 95% máx. (%)", "Observação",
        ]
    )
    geral = {"contagem": analise["contagem_geral"], **analise["geral"]}
    escritor.writerow(_linha("Carteira", "Total", geral))
    for item in analise["por_vara"]:
        escritor.writerow(_linha("Vara", item["vara"], item))
    for item in analise["por_ano"]:
        escritor.writerow(_linha("Ano", item["ano"] or "Sem data", item))
    return "﻿" + saida.getvalue()


def descrever_recorte(filtros):
    partes = []
    if "area" in filtros:
        partes.append(f"Área: {dict(Processo.AREA_CHOICES)[filtros['area']]}")
    if "ano" in filtros:
        partes.append("Sem data de distribuição" if filtros["ano"] == SEM_DATA else f"Ano: {filtros['ano']}")
    return "; ".join(partes) or "Carteira completa"
