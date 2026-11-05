"""Taxas com o contexto que a torna honesta: quantos casos, qual a incerteza.

Nenhum percentual sai daqui sozinho. Abaixo do piso de amostra a taxa é
suprimida, com o motivo, em vez de exibida frágil: 1 favorável em 1 processo é
"100%" na conta, mas não diz nada sobre a vara.
"""

from math import sqrt


def intervalo_wilson(sucessos, total, z=1.96):
    """Intervalo de confiança de 95% para uma proporção, em escala 0 a 1.

    Wilson, e não a aproximação normal: ela dá intervalos impossíveis (negativos
    ou acima de 100%) justamente com amostras pequenas e taxas extremas, que é
    o caso comum aqui.
    """
    if total <= 0:
        return (0.0, 1.0)
    p = sucessos / total
    denominador = 1 + z**2 / total
    centro = (p + z**2 / (2 * total)) / denominador
    margem = z * sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denominador
    return (max(0.0, centro - margem), min(1.0, centro + margem))


def taxa_com_contexto(favoraveis, total, *, piso):
    """Taxa favorável com n e intervalo, ou suprimida com o motivo.

    Percentuais inteiros; `desfavoravel` é o complemento, para somar 100.
    """
    if total < piso:
        return {
            "total": total,
            "suficiente": False,
            "favoravel": None,
            "desfavoravel": None,
            "intervalo_favoravel": None,
            "motivo": f"Amostra insuficiente: {total} de no mínimo {piso} processos.",
        }
    minimo, maximo = intervalo_wilson(favoraveis, total)
    favoravel = round(favoraveis / total * 100)
    return {
        "total": total,
        "suficiente": True,
        "favoravel": favoravel,
        "desfavoravel": 100 - favoravel,
        "intervalo_favoravel": {"min": round(minimo * 100), "max": round(maximo * 100)},
        "motivo": None,
    }
