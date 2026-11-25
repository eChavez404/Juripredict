"""Jurimetria do tribunal: sentenças públicas do TRT-16, não processos do escritório.

A base vem do pipeline (`dataset/pipeline/exportar_jurimetria.py`), importada por
`importar_decisoes_trt`. A taxa segue a regra da jurimetria da carteira (n, intervalo e
piso) e duas travas a mais, do desenho do produto: só aparece depois que o rótulo
automático for conferido por leitura humana (gold set) e com a cobertura da fonte medida
naquele recorte (I3). Até lá, a tela mostra quantas decisões existem e deixa lê-las.
"""

import csv
from datetime import date

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Min
from rest_framework.exceptions import ValidationError

from .estatistica import taxa_com_contexto
from .models import DecisaoTribunal, LoteDecisoesTribunal

RESULTADOS = ("deferido", "indeferido")
COLUNAS = {
    "caso_id", "numero_cnj", "tema", "vara", "data_sentenca", "resultado", "grau",
    "populacao", "motivo_fora", "mecanismo", "trecho", "versao",
}
LIMITE_LISTA = 200

POPULACAO = (
    "Pedidos julgados no mérito em sentença de 1º grau do TRT-16. Não é probabilidade de "
    "êxito ao ajuizar: acordos e desistências não chegam a esta conta."
)
CRITERIO = (
    "Mesmo pedido e, quando escolhidos, mesma vara e mesmo ano da sentença. As decisões são "
    "agrupadas por esses filtros, não por semelhança entre os fatos dos casos."
)
FORA_DA_TAXA = {
    "ambiguo": "Procedência parcial sem dizer se este pedido foi deferido",
    "nao_analisado": "Pedido não julgado no mérito (desistência, extinção)",
    "nao_mencionado": "O dispositivo não trata do pedido",
    "acao_coletiva": "Ação coletiva (sindicato ou Ministério Público)",
    "EXECUCAO": "Execução de sentença",
    "LIQUIDACAO": "Liquidação",
    "EMBARGOS_DECLARACAO": "Embargos de declaração",
    "HOMOLOGATORIA": "Acordo homologado",
}


# ----------------------------------------------------------------- importação
def importar(arquivo, *, validacao=None):
    """Troca a base inteira pela do arquivo, numa transação: ou entra tudo, ou nada muda."""
    leitor = csv.DictReader(arquivo)
    faltando = COLUNAS - set(leitor.fieldnames or ())
    if faltando:
        raise ValueError(f"Colunas ausentes no arquivo: {', '.join(sorted(faltando))}.")
    temas = dict(DecisaoTribunal.TEMAS)
    decisoes = []
    for numero, linha in enumerate(leitor, start=2):
        if linha["tema"] not in temas:
            raise ValueError(f"Linha {numero}: tema desconhecido ({linha['tema']}).")
        decisoes.append(
            DecisaoTribunal(
                caso_id=linha["caso_id"],
                numero_cnj=linha["numero_cnj"],
                tema=linha["tema"],
                vara=linha["vara"],
                data_sentenca=date.fromisoformat(linha["data_sentenca"]) if linha["data_sentenca"] else None,
                resultado=linha["resultado"],
                grau=int(linha["grau"]) if linha["grau"] else None,
                populacao=linha["populacao"],
                motivo_fora=linha["motivo_fora"],
                mecanismo=linha["mecanismo"],
                trecho=linha["trecho"],
                versao=linha["versao"],
            )
        )
    if not decisoes:
        raise ValueError("O arquivo não tem nenhuma decisão.")
    with transaction.atomic():
        DecisaoTribunal.objects.all().delete()
        DecisaoTribunal.objects.bulk_create(decisoes, batch_size=1000)
        lote = LoteDecisoesTribunal.objects.create(
            versao=decisoes[0].versao, total=len(decisoes), validacao=validacao or {}
        )
    return lote


# ---------------------------------------------------------------- validação
def estado_da_validacao(lote):
    """O que libera a taxa: rótulo conferido por leitura humana e cobertura medida."""
    gold = (lote.validacao or {}).get("gold_set") if lote else None
    minimo = settings.JURIMETRIA_TRT_GOLD_MINIMO
    conferido = bool(gold) and gold.get("anotados", 0) >= minimo and min(
        gold.get("concordancia_deferido", 0), gold.get("concordancia_indeferido", 0)
    ) >= settings.JURIMETRIA_TRT_CONCORDANCIA_MINIMA
    if conferido:
        motivo = None
    elif not gold:
        motivo = (
            "O resultado de cada decisão foi lido por regra automática e ainda não foi "
            f"conferido por leitura humana (gold set com no mínimo {minimo} decisões)."
        )
    else:
        motivo = (
            "A conferência humana do rótulo não atingiu a concordância mínima, ou tem menos de "
            f"{minimo} decisões. A regra precisa ser revista antes de exibir taxas."
        )
    cobertura = (lote.validacao or {}).get("cobertura") if lote else None
    return {"rotulo_conferido": conferido, "gold_set": gold, "motivo": motivo, "cobertura": cobertura or {}}


def _taxa(contagem, recorte, validacao, piso):
    deferidos = contagem.get("deferido", 0)
    total = deferidos + contagem.get("indeferido", 0)
    taxa = taxa_com_contexto(deferidos, total, piso=piso)
    cobertura = validacao["cobertura"].get(recorte)
    taxa["cobertura"] = cobertura
    if taxa["suficiente"] and (not validacao["rotulo_conferido"] or cobertura is None):
        motivo = validacao["motivo"] or "Cobertura da fonte neste recorte ainda não medida."
        taxa.update(favoravel=None, desfavoravel=None, intervalo_favoravel=None, motivo=motivo)
    return taxa


# ------------------------------------------------------------------- consulta
def filtros_da_requisicao(parametros, *, com_resultado=False):
    tema = parametros.get("tema") or DecisaoTribunal.TEMAS[0][0]
    if tema not in dict(DecisaoTribunal.TEMAS):
        raise ValidationError({"tema": ["Tema inválido."]})
    filtros = {"tema": tema}
    ano = parametros.get("ano")
    if ano:
        if not (ano.isascii() and ano.isdigit() and 1900 <= int(ano) <= 2100):
            raise ValidationError({"ano": ["Informe um ano válido."]})
        filtros["ano"] = int(ano)
    if parametros.get("vara"):
        filtros["vara"] = parametros["vara"]
    resultado = parametros.get("resultado")
    if com_resultado and resultado:
        if resultado not in RESULTADOS:
            raise ValidationError({"resultado": ["Resultado inválido."]})
        filtros["resultado"] = resultado
    return filtros


def _recorte(filtros):
    decisoes = DecisaoTribunal.objects.filter(tema=filtros["tema"])
    if "vara" in filtros:
        decisoes = decisoes.filter(vara=filtros["vara"])
    if "ano" in filtros:
        decisoes = decisoes.filter(data_sentenca__year=filtros["ano"])
    return decisoes


def _contagens(decisoes, campo):
    grupos = {}
    for linha in decisoes.values(campo, "resultado").annotate(n=Count("id")).order_by():
        grupos.setdefault(linha[campo], {})[linha["resultado"]] = linha["n"]
    return grupos


def analisar(filtros):
    lote = LoteDecisoesTribunal.objects.order_by("-importado_em", "-id").first()
    if lote is None:
        return {"disponivel": False}
    piso = settings.JURIMETRIA_PISO_AMOSTRA
    validacao = estado_da_validacao(lote)
    tema = DecisaoTribunal.objects.filter(tema=filtros["tema"])
    decisoes = _recorte(filtros)
    na_taxa = decisoes.filter(populacao="modelo", resultado__in=RESULTADOS)

    geral = {}
    for linha in na_taxa.values("resultado").annotate(n=Count("id")).order_by():
        geral[linha["resultado"]] = linha["n"]
    recorte_geral = filtros.get("vara", "geral")

    fora = {}
    for linha in decisoes.exclude(populacao="modelo").values("motivo_fora").annotate(n=Count("id")):
        rotulo = FORA_DA_TAXA.get(linha["motivo_fora"], "Outro motivo")
        fora[rotulo] = fora.get(rotulo, 0) + linha["n"]

    por_vara = sorted(
        (
            {"vara": vara, **_taxa(contagem, vara, validacao, piso)}
            for vara, contagem in _contagens(na_taxa, "vara").items()
        ),
        key=lambda item: (-item["total"], item["vara"]),
    )
    por_ano = sorted(
        (
            {"ano": ano, **_taxa(contagem, f"ano:{ano}", validacao, piso)}
            for ano, contagem in _contagens(na_taxa, "data_sentenca__year").items()
            if ano is not None
        ),
        key=lambda item: -item["ano"],
    )
    periodo = tema.aggregate(inicio=Min("data_sentenca"), fim=Max("data_sentenca"))
    return {
        "disponivel": True,
        "filtros": filtros,
        "geral": _taxa(geral, recorte_geral, validacao, piso),
        "fora_da_taxa": [{"motivo": motivo, "total": n} for motivo, n in sorted(fora.items(), key=lambda i: -i[1])],
        "por_vara": por_vara,
        "por_ano": por_ano,
        "validacao": {
            "rotulo_conferido": validacao["rotulo_conferido"],
            "motivo": validacao["motivo"],
            "gold_set": validacao["gold_set"],
            "cobertura_medida": bool(validacao["cobertura"]),
        },
        "opcoes": {
            "temas": [{"valor": valor, "rotulo": rotulo} for valor, rotulo in DecisaoTribunal.TEMAS],
            "varas": sorted(v for v in tema.values_list("vara", flat=True).distinct() if v),
            "anos": sorted(
                {d.year for d in tema.exclude(data_sentenca=None).dates("data_sentenca", "year")},
                reverse=True,
            ),
        },
        "fonte": {
            "origem": "Falcão (CSJT): sentenças públicas do TRT da 16ª Região",
            "inicio": periodo["inicio"],
            "fim": periodo["fim"],
            "versao": lote.versao,
            "importado_em": lote.importado_em,
        },
        "populacao": POPULACAO,
        "criterio": CRITERIO,
        "piso_amostra": piso,
    }


def decisoes_do_recorte(filtros):
    """As decisões que sustentam o número do recorte, com o trecho do dispositivo."""
    na_taxa = _recorte(filtros).filter(populacao="modelo", resultado__in=RESULTADOS)
    contagem = {
        linha["resultado"]: linha["n"]
        for linha in na_taxa.values("resultado").annotate(n=Count("id")).order_by()
    }
    if "resultado" in filtros:
        na_taxa = na_taxa.filter(resultado=filtros["resultado"])
    lista = na_taxa.order_by("-data_sentenca", "numero_cnj")
    total = lista.count()
    campos = ("numero_cnj", "vara", "data_sentenca", "resultado", "grau", "mecanismo", "trecho")
    itens = list(lista.values(*campos)[:LIMITE_LISTA])
    return {"total": total, "exibidos": len(itens), "contagem": contagem, "decisoes": itens}
