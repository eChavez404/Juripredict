"""Contagem de prazos processuais em dias úteis, com a memória do cálculo.

Regra de segurança: errar para antes, nunca para depois. Só deixa de ser contado o dia que
com certeza não corre (fim de semana, feriado nacional em lei, suspensão de 20/12 a 20/1).
O dia em que os tribunais costumam suspender, mas que depende de ato de cada um (Carnaval,
Semana Santa, Corpus Christi), é contado e devolvido em ``dias_a_conferir``: quem calcula
confere o calendário do tribunal e o informa em ``suspensoes``, e a data recua no máximo
para o que foi informado.

Base: CLT, arts. 775 e 775-A; CPC, arts. 216, 219, 220 e 224; Lei 11.419/2006, art. 4º, §§ 3º
e 4º; TST, Súmulas 1 e 262; Leis 662/1949, 6.802/1980 e 14.759/2023 (feriados nacionais).
"""

from datetime import date, timedelta
from functools import lru_cache

INTIMACAO = "INTIMACAO"
PUBLICACAO_DIARIO = "PUBLICACAO_DIARIO"

FUNDAMENTOS = {
    "TRABALHISTA": "CLT, arts. 775 e 775-A; TST, Súmulas 1 e 262; Lei 11.419/2006, art. 4º",
    "CIVEL": "CPC, arts. 216, 219, 220 e 224; Lei 11.419/2006, art. 4º",
}

RECESSO = "Suspensão de 20/12 a 20/1"
INFORMADO = "Sem expediente, conforme informado"
RESSALVA_GERAL = (
    "Cálculo de apoio: confira o calendário do tribunal. Feriados estaduais e municipais e "
    "pontos facultativos não entram na conta sozinhos, então o prazo real pode terminar depois "
    "desta data, nunca antes por causa deles. Prazo fixado pelo juiz, prazo em dobro e "
    "indisponibilidade do sistema também não são considerados."
)
RESSALVA_CIENCIA_NA_SUSPENSAO = (
    "A ciência ocorreu durante a suspensão de 20/12 a 20/1: a contagem assume início no primeiro "
    "dia útil seguinte a ela. Confira se o tribunal adota outro critério para este ato."
)


def pascoa(ano):
    """Domingo de Páscoa no calendário gregoriano (algoritmo anônimo de Meeus)."""
    a = ano % 19
    b, c = divmod(ano, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(ano, mes, dia + 1)


@lru_cache(maxsize=32)
def feriados_nacionais(ano):
    feriados = {
        date(ano, 1, 1): "Confraternização Universal",
        date(ano, 4, 21): "Tiradentes",
        date(ano, 5, 1): "Dia do Trabalho",
        date(ano, 9, 7): "Independência do Brasil",
        date(ano, 10, 12): "Nossa Senhora Aparecida",
        date(ano, 11, 2): "Finados",
        date(ano, 11, 15): "Proclamação da República",
        date(ano, 12, 25): "Natal",
    }
    if ano >= 2024:  # Lei 14.759, de dezembro de 2023
        feriados[date(ano, 11, 20)] = "Consciência Negra"
    return feriados


@lru_cache(maxsize=32)
def dias_a_conferir_no_ano(ano):
    """Dias sem certeza nacional: dependem de ato do tribunal (Lei 5.010/1966, art. 62, na JF)."""
    domingo = pascoa(ano)
    return {
        domingo - timedelta(days=48): "Segunda-feira de Carnaval",
        domingo - timedelta(days=47): "Terça-feira de Carnaval",
        domingo - timedelta(days=46): "Quarta-feira de Cinzas",
        domingo - timedelta(days=4): "Quarta-feira da Semana Santa",
        domingo - timedelta(days=3): "Quinta-feira Santa",
        domingo - timedelta(days=2): "Sexta-feira da Paixão",
        domingo + timedelta(days=60): "Corpus Christi",
        date(ano, 8, 11): "Dia do Advogado",
        date(ano, 10, 28): "Dia do Servidor Público",
        date(ano, 11, 1): "Dia de Todos os Santos",
        date(ano, 12, 8): "Dia da Justiça",
    }


def em_suspensao(dia):
    return (dia.month, dia.day) >= (12, 20) or (dia.month, dia.day) <= (1, 20)


def _motivo_de_nao_correr(dia, suspensoes):
    if dia in suspensoes:
        return INFORMADO
    if em_suspensao(dia):
        return RECESSO
    feriado = feriados_nacionais(dia.year).get(dia)
    if feriado:
        return f"Feriado nacional: {feriado}"
    if dia.weekday() >= 5:
        return "Fim de semana"
    return None


def _proximo_dia_util(dia, suspensoes):
    dia += timedelta(days=1)
    while _motivo_de_nao_correr(dia, suspensoes):
        dia += timedelta(days=1)
    return dia


def calcular_prazo(*, data_base, dias, tipo=INTIMACAO, area="TRABALHISTA", suspensoes=()):
    """Vencimento e memória do cálculo.

    ``data_base`` é a data da ciência (``INTIMACAO``) ou da disponibilização no diário
    eletrônico (``PUBLICACAO_DIARIO``). O dia do começo não conta; o do vencimento conta.
    """
    suspensoes = frozenset(suspensoes)

    if tipo == PUBLICACAO_DIARIO:
        # Disponibilizado hoje, publicado no dia útil seguinte; a contagem começa depois dele.
        marco = _proximo_dia_util(data_base, suspensoes)
    elif _motivo_de_nao_correr(data_base, suspensoes):
        # Ciência em dia sem expediente vale no primeiro dia útil seguinte (Súmula 262, I).
        marco = _proximo_dia_util(data_base, suspensoes)
    else:
        marco = data_base

    vencimento = marco
    for _ in range(dias):
        vencimento = _proximo_dia_util(vencimento, suspensoes)

    nao_contados, a_conferir, fins_de_semana = [], [], 0
    dia = data_base
    while dia <= vencimento:
        motivo = _motivo_de_nao_correr(dia, suspensoes)
        if motivo == "Fim de semana":
            fins_de_semana += 1
        elif motivo:
            nao_contados.append({"data": dia, "motivo": motivo})
        else:
            duvida = dias_a_conferir_no_ano(dia.year).get(dia)
            if duvida:
                a_conferir.append({"data": dia, "motivo": duvida})
        dia += timedelta(days=1)

    ressalvas = [RESSALVA_GERAL]
    if tipo == INTIMACAO and em_suspensao(data_base):
        ressalvas.append(RESSALVA_CIENCIA_NA_SUSPENSAO)

    return {
        "data_base": data_base,
        "dias": dias,
        "tipo": tipo,
        "area": area,
        "fundamento": FUNDAMENTOS[area],
        "marco_inicial": marco,
        "primeiro_dia_contado": _proximo_dia_util(marco, suspensoes),
        "vencimento": vencimento,
        "fins_de_semana_nao_contados": fins_de_semana,
        "dias_nao_contados": nao_contados,
        "dias_a_conferir": a_conferir,
        "ressalvas": ressalvas,
    }
