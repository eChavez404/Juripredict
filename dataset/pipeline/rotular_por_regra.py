"""
Extrai o label direto do dispositivo, por regra. Sem LLM, custo zero.
Cobre a camada 2 do pipeline: roda no corpus inteiro.

Rodar sozinho executa os testes embutidos:
    python rotular_por_regra.py
"""

import os
import re
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# VERSAO DO DATASET
#
# "1.0"  reproduz o estado publicado na monografia: 623 casos, 376 registros,
#        22 unidades, taxa-base 72,6%.
# "2.0"  aplica as tres correcoes de coerencia encontradas em revisao.
#
# O que a 2.0 corrige, e que a 1.0 deixa passar:
#
#   17 casos de INCORPORACAO DE GRATIFICACAO em que "insalubridade" aparece
#      apenas na lista de parcelas que recebem reflexo da gratificacao. Nao sao
#      pedidos de adicional; 16 estavam rotulados `deferido` e sozinhos
#      respondem pela maior parte da diferenca entre 72,6% e 68,2%.
#
#    3 casos em que o dispositivo EXTINGUE o pedido de insalubridade sem
#      resolucao do merito - inepcia, litispendencia - e o rotulo dizia que
#      fora julgado.
#
#   15 ACOES COLETIVAS (sindicato, associacao ou MPT no polo ativo). A decisao
#      alcanca os substituidos da categoria inteira: uma linha nao representa um
#      pedido de um trabalhador, e pesa igual a um caso singular em qualquer
#      taxa por vara.
#
# Trocar para "2.0" aqui, ou exportar JURIPREDICT_VERSAO=2.0, reativa as tres.
# As regras continuam escritas e testadas nos dois modos.
# ---------------------------------------------------------------------------
VERSAO_DATASET = os.environ.get("JURIPREDICT_VERSAO", "1.0").strip().lstrip("vV")

# Comparacao NUMERICA, nao lexicografica. `"10.0" >= "2.0"` e False em string:
# uma versao 10 desligaria as correcoes em silencio. E `"v2.0" >= "2.0"` era
# True por acidente, pelo 'v' ordenar depois dos digitos.
try:
    _partes = tuple(int(p) for p in VERSAO_DATASET.split("."))
except ValueError:
    raise SystemExit(f"JURIPREDICT_VERSAO invalida: {VERSAO_DATASET!r} "
                     f"(esperado algo como 1.0 ou 2.0)")
CORRIGE_COERENCIA = _partes >= (2, 0)

# ---------------------------------------------------------------------------
# Resultado global da acao. A ordem importa: 'improcedente' e 'em parte' sao
# testados antes do 'procedente' generico.
# ---------------------------------------------------------------------------

# Formas verbais reais observadas nos dispositivos do TRT-16:
#   "decido julgar PARCIALMENTE PROCEDENTES"
#   "No merito, julgar PROCEDENTES"
#   "julgo IMPROCEDENTES"
# A primeira versao so cobria JULGO, e por isso devolvia "indefinido" na
# maioria dos casos reais.
_JULGAR = r"(?:JULG(?:O|AR|UE-SE|AM-SE|A-SE)|DECIDO\s+JULGAR)"

REGRAS_GLOBAIS = [
    ("acordo", re.compile(
        r"HOMOLOGO\s+(?:O\s+)?(?:ACORDO|A\s+TRANSA[\u00c7C][\u00c3A]O|A\s+CONCILIA[\u00c7C][\u00c3A]O)",
        re.IGNORECASE)),
    ("extinto_sem_merito", re.compile(
        # "extinguir" aparece no corpus tanto quanto "extingo": o dispositivo
        # real escreve "decido homologar a desistencia ... e EXTINGUIR o feito
        # sem resolucao do merito". So com GO/CAO o caso caia em "indefinido".
        r"EXTIN(?:GO|GUIR|GUE-SE|GUINDO|[\u00c7C][\u00c3A]O)\s+"
        r".{0,60}SEM\s+(?:RESOLU[\u00c7C][\u00c3A]O|JULGAMENTO)\s+"
        r"(?:DO\s+)?M[\u00c9E]RITO",
        re.IGNORECASE | re.DOTALL)),
    ("parcialmente_procedente", re.compile(
        rf"{_JULGAR}\s+.{{0,60}}?(?:PROCEDENTES?\s+EM\s+PARTE"
        rf"|PARCIALMENTE\s*\n?\s*PROCEDENTES?)",
        re.IGNORECASE | re.DOTALL)),
    ("improcedente", re.compile(
        rf"{_JULGAR}\s+.{{0,60}}?IMPROCEDENTES?\b", re.IGNORECASE | re.DOTALL)),
    ("procedente", re.compile(
        rf"{_JULGAR}\s+.{{0,60}}?PROCEDENTES?\b", re.IGNORECASE | re.DOTALL)),
]

TEMAS = {
    "insalubridade": r"INSALUBR\w*",
    "periculosidade": r"PERICULOS\w*",
    "horas_extras": r"HORAS?\s+EXTRAS?|SOBREJORNADA",
}

DEFERE = re.compile(
    r"\b(?:DEFIRO|DEFERE|DEFERID\w+|CONDEN\w+|ACOLH\w+|PROCEDENTES?)\b",
    re.IGNORECASE)
INDEFERE = re.compile(
    r"\b(?:INDEFIRO|INDEFERE|INDEFERID\w+|INDEFERINDO|IMPROCEDENTES?|REJEIT\w+"
    r"|N[\u00c3A]O\s+ACOLH\w+|AUS[\u00caE]NCIA\s+DE\s+DIREITO|ABSOLV\w+)\b",
    re.IGNORECASE)

GRAUS = [
    (40, re.compile(r"GRAU\s+M[\u00c1A]XIMO|\b40\s*%", re.IGNORECASE)),
    (20, re.compile(r"GRAU\s+M[\u00c9E]DIO|\b20\s*%", re.IGNORECASE)),
    (10, re.compile(r"GRAU\s+M[\u00cdI]NIMO|\b10\s*%", re.IGNORECASE)),
]

# Oracao que so CITA a materia - precedente, sumula, norma regulamentadora -
# sem decidir nada sobre o pedido. Sem isso, a mencao ao tema dentro da citacao
# puxava o verbo decisorio da oracao vizinha e o caso virava ambiguo:
#   "... os parametros definidos na decisao do STF acerca da materia
#    (adicional de insalubridade) e no julgamento da ADI 6021"
CITACAO = re.compile(
    r"\b(?:ADI|ADC|ADPF|RE|A[\u00cdI]RR?|RR|TST|STF|STJ|S[\u00daU]MULA|"
    r"OJ|ORIENTA[\u00c7C][\u00c3A]O\s+JURISPRUDENCIAL|TEMA\s+\d|"
    r"NR[\s-]?15|ANEXO\s+\d|PRECEDENTE|ART(?:IGO)?\.?\s*\d)\b",
    re.IGNORECASE)

# Desistencia ou renuncia do proprio pedido: o merito nao chega a ser julgado.
# E classe de escape (I1), nao empate entre verbos opostos.
DESISTENCIA = re.compile(
    r"\b(?:DESIST[\u00caE]NCIA|DESISTIU|REN[\u00daU]NCIA|RENUNCIOU)\b",
    re.IGNORECASE)

# Extincao sem resolucao do merito, inepcia, litispendencia. Tambem escape.
EXTINCAO = re.compile(
    r"EXTIN\w+.{0,120}SEM\s+RESOLU[\u00c7C][\u00c3A]O.{0,40}M[\u00c9E]RITO"
    r"|IN[\u00c9E]PCIA.{0,120}EXTIN\w+"
    r"|EXTIN\w+.{0,80}QUANTO\s+AO\s+PEDIDO", re.IGNORECASE | re.DOTALL)

# O tema aparecendo como BASE de reflexo de outra verba - nao como o pedido.
#
#   "reflexos sobre FGTS, 13o salario, ferias + 1/3, anuenio, adicionais de
#    insalubridade ou periculosidade, adicional noturno"
#
# Aqui quem foi deferido e a gratificacao; a insalubridade so consta da lista de
# parcelas sobre as quais ela repercute. Sem distinguir isso, 17 sentencas de
# incorporacao de gratificacao entravam como deferimento de insalubridade e
# inflavam a taxa-base.
CONTEXTO_DE_REFLEXO = re.compile(
    r"(?:REFLEXOS?|REPERCUSS\w+|INCORPORA\w+|INTEGRA\w+)\s+"
    r"(?:SOBRE|EM|NOS?|NAS?|D[OA]S?)?[^.;]{0,120}$", re.IGNORECASE)


def _so_base_de_reflexo(texto, padrao_tema) -> bool:
    """True quando TODA mencao ao tema no texto esta em contexto de reflexo."""
    marcas = list(padrao_tema.finditer(texto or ""))
    if not marcas:
        return False
    return all(CONTEXTO_DE_REFLEXO.search(texto[max(0, m.start() - 160):m.start()])
               for m in marcas)

# Frase de fecho do capitulo da fundamentacao. So e consultada quando o
# dispositivo NAO nomeia o pedido - ver a nota em `rotular`.
FECHO_DEFERE = re.compile(
    r"\b(?:DEFIRO|JULGO\s+PROCEDENTE|ACOLHO|PROCEDE\s+O\s+PEDIDO|"
    r"FA[\u00c7C]O\s+JUS|DEVIDO\s+O\s+ADICIONAL|CONDENO)\b", re.IGNORECASE)
FECHO_INDEFERE = re.compile(
    r"\b(?:INDEFIRO|JULGO\s+IMPROCEDENTE|REJEITO|N[\u00c3A]O\s+ACOLHO|"
    r"N[\u00c3A]O\s+PROCEDE|N[\u00c3A]O\s+FAZ\s+JUS|N[\u00c3A]O\s+[\u00c9E]\s+DEVIDO|"
    r"IMPROCEDE)\b", re.IGNORECASE)


@dataclass
class Rotulo:
    resultado_global: str = "indefinido"
    resultado_pedido: str = "nao_mencionado"   # deferido / indeferido / ambiguo
    grau: Optional[int] = None
    trecho: str = ""                            # evidencia, para conferencia manual


def resultado_global(dispositivo: str) -> str:
    for nome, padrao in REGRAS_GLOBAIS:
        if padrao.search(dispositivo):
            return nome
    return "indefinido"


JANELA_ANTERIOR = 6   # oracoes COM conteudo para tras, ao procurar o verbo regente

# Marcador de item de lista: "a)", "1.", "-", "IV -". Um item so enumera uma
# verba; nao gasta orcamento da janela, senao um dispositivo com dez verbas
# esgota a busca antes de chegar ao verbo que abre a lista.
ITEM_DE_LISTA = re.compile(
    r"^\s*(?:[a-z]\)|\(?[a-z]\)|\d+[\).\-]|[ivxlcdm]+\s*[\).\-]|[-–•*])\s*",
    re.IGNORECASE)


def _clausulas(texto: str):
    """Quebra o dispositivo em oracoes curtas para nao misturar pedidos."""
    partes = re.split(r"[;.]\s+|\n", texto)
    return [p.strip() for p in partes if p.strip()]


def _verbo_regente(clausulas, indice):
    """
    Procura o verbo decisorio nas oracoes anteriores.

    Existe porque o dispositivo real lista as verbas em itens, e o verbo fica
    no paragrafo que abre a lista:

        ... para condenar a reclamada ao pagamento das seguintes verbas:
        - Adicional de insalubridade durante todo o periodo laborado ...

    O item sozinho nao tem verbo. Sem olhar para tras, vira "ambiguo".
    """
    orcamento = JANELA_ANTERIOR
    for i in range(indice - 1, -1, -1):
        anterior = clausulas[i]
        tem_defere = DEFERE.search(anterior)
        tem_indefere = INDEFERE.search(anterior)
        if tem_defere and not tem_indefere:
            return "deferido"
        if tem_indefere and not tem_defere:
            return "indeferido"
        if tem_defere and tem_indefere:
            return None      # oracao anterior ambigua: nao arrisca

        # item de enumeracao sem verbo proprio nao consome a janela
        if not ITEM_DE_LISTA.match(anterior):
            orcamento -= 1
            if orcamento <= 0:
                return None
    return None


def _decidir_clausula(clausula: str, padrao_tema) -> Optional[str]:
    """Decide pelo verbo mais proximo da mencao ao tema dentro da oracao."""
    m_tema = padrao_tema.search(clausula)
    if not m_tema:
        return None
    pos = m_tema.start()

    candidatos = [(abs(m.start() - pos), "deferido") for m in DEFERE.finditer(clausula)]
    candidatos += [(abs(m.start() - pos), "indeferido") for m in INDEFERE.finditer(clausula)]
    if not candidatos:
        return None

    candidatos.sort()
    if (len(candidatos) > 1
            and candidatos[0][1] != candidatos[1][1]
            and candidatos[1][0] - candidatos[0][0] < 15):
        return "ambiguo"   # empate tecnico entre verbos opostos
    return candidatos[0][1]


def _decide_na_fundamentacao(fundamentacao: str, padrao_tema) -> Optional[str]:
    """
    Ultimo recurso, so quando o dispositivo NAO nomeia o pedido.

    O capitulo da fundamentacao costuma fechar com a decisao explicita
    ("Pelo exposto, indefiro o adicional de insalubridade"), e essa frase e
    tao decisoria quanto o dispositivo. Le-se apenas a oracao que menciona o
    tema E carrega verbo de fecho; qualquer conflito devolve None, para o caso
    continuar ambiguo em vez de virar chute.
    """
    decisoes = set()
    for c in _clausulas(fundamentacao):
        if not padrao_tema.search(c) or CITACAO.search(c):
            continue
        d, i = FECHO_DEFERE.search(c), FECHO_INDEFERE.search(c)
        if d and not i:
            decisoes.add("deferido")
        elif i and not d:
            decisoes.add("indeferido")
        elif d and i:
            return None
    return decisoes.pop() if len(decisoes) == 1 else None


def rotular(dispositivo: str, tema: str, fundamentacao: str = "") -> Rotulo:
    if tema not in TEMAS:
        raise ValueError(f"tema desconhecido: {tema}")

    r = Rotulo(resultado_global=resultado_global(dispositivo))
    padrao_tema = re.compile(TEMAS[tema], re.IGNORECASE)

    clausulas = _clausulas(dispositivo)
    relevantes = [c for c in clausulas if padrao_tema.search(c)]

    # Desistencia homologada do proprio pedido: nao houve julgamento de merito
    # sobre ele. Classe de escape, nao empate entre verbos.
    if any(DESISTENCIA.search(c) for c in relevantes):
        r.resultado_pedido = "nao_analisado"
        r.trecho = next(c for c in relevantes if DESISTENCIA.search(c))[:400]
        return r

    if CORRIGE_COERENCIA:
        # O tema so aparece como base de reflexo de OUTRA verba: nao e o pedido
        # julgado aqui. Precede a extincao porque nem chega a haver pedido.
        if _so_base_de_reflexo(dispositivo, padrao_tema):
            r.resultado_pedido = "nao_mencionado"
            r.trecho = "tema citado apenas como base de reflexo de outra verba"
            return r

        # Extincao sem merito DO PROPRIO pedido. Distingue-se de extinguir os
        # REFLEXOS dele, que deixa o adicional em si por julgar: por isso a
        # mencao ao tema nao pode estar em contexto de reflexo na mesma oracao.
        for c in relevantes:
            if not EXTINCAO.search(c):
                continue
            m = padrao_tema.search(c)
            if m and not CONTEXTO_DE_REFLEXO.search(
                    c[max(0, m.start() - 160):m.start()]):
                r.resultado_pedido = "nao_analisado"
                r.trecho = c[:400]
                return r

    if not relevantes:
        # O dispositivo nao nomeia o pedido. Ha assimetria estrutural aqui:
        # deferir obriga a especificar o que se paga, indeferir nao — basta
        # "julgo IMPROCEDENTES os pedidos". Sem tratar isso, a classe negativa
        # desaparece do dataset.
        #
        # So se infere quando o resultado global e TOTAL e o tema aparece na
        # fundamentacao. Procedencia parcial fica ambigua de proposito: "parte"
        # pode ou nao incluir a insalubridade.
        if fundamentacao and padrao_tema.search(fundamentacao):
            if r.resultado_global == "improcedente":
                r.resultado_pedido = "indeferido"
                r.trecho = "inferido: improcedencia total, tema na fundamentacao"
            elif r.resultado_global == "procedente":
                r.resultado_pedido = "deferido"
                r.trecho = "inferido: procedencia total, tema na fundamentacao"
            elif r.resultado_global == "parcialmente_procedente":
                # "Parte" pode ou nao incluir a insalubridade, e o dispositivo
                # nao diz. Antes de desistir, le-se a frase de fecho do capitulo
                # da fundamentacao, que decide o pedido com as mesmas palavras.
                # So vale se for inequivoca; qualquer conflito mantem ambiguo.
                decidido = _decide_na_fundamentacao(fundamentacao, padrao_tema)
                if decidido:
                    r.resultado_pedido = decidido
                    r.trecho = ("inferido: procedencia parcial, fecho do "
                                f"capitulo indica {decidido}")
                else:
                    r.resultado_pedido = "ambiguo"
                    r.trecho = "procedencia parcial sem nomear o pedido"
        return r

    r.trecho = " | ".join(relevantes)[:400]

    decisoes = set()
    for i, c in enumerate(clausulas):
        if not padrao_tema.search(c):
            continue
        # oracao que so cita precedente ou norma nao decide o pedido, e puxaria
        # o verbo da oracao vizinha por proximidade
        if CITACAO.search(c) and _decidir_clausula(c, padrao_tema) is None:
            continue
        d = _decidir_clausula(c, padrao_tema)
        if d is None:
            # item de lista sem verbo proprio: quem decide e a oracao que abre
            d = _verbo_regente(clausulas, i)
        if d is not None:
            decisoes.add(d)

    if decisoes == {"deferido"}:
        r.resultado_pedido = "deferido"
    elif decisoes == {"indeferido"}:
        r.resultado_pedido = "indeferido"
    else:
        # sem verbo decisorio, ou verbos conflitantes: manda para a camada 3 (LLM)
        r.resultado_pedido = "ambiguo"

    if r.resultado_pedido == "deferido" and tema in ("insalubridade", "periculosidade"):
        for valor, padrao in GRAUS:
            if any(padrao.search(c) for c in relevantes):
                r.grau = valor
                break

    return r


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

CASOS = [
    (
        "Ante o exposto, julgo PROCEDENTES EM PARTE os pedidos para condenar a "
        "reclamada ao pagamento do adicional de insalubridade em grau medio (20%) "
        "e das horas extras excedentes da 8a diaria. Custas pela reclamada.",
        "insalubridade",
        dict(resultado_global="parcialmente_procedente", resultado_pedido="deferido", grau=20),
    ),
    (
        "Ante o exposto, julgo IMPROCEDENTES os pedidos. Indefiro o adicional de "
        "periculosidade. Custas pelo reclamante, dispensadas.",
        "periculosidade",
        dict(resultado_global="improcedente", resultado_pedido="indeferido", grau=None),
    ),
    (
        "Isto posto, julgo PROCEDENTE EM PARTE a reclamacao; defiro as horas extras "
        "alem da 44a semanal; indefiro o adicional de insalubridade, por ausencia de "
        "direito reconhecida em laudo.",
        "insalubridade",
        dict(resultado_global="parcialmente_procedente", resultado_pedido="indeferido", grau=None),
    ),
    (
        "Isto posto, julgo PROCEDENTE EM PARTE a reclamacao; defiro as horas extras "
        "alem da 44a semanal; indefiro o adicional de insalubridade.",
        "horas_extras",
        dict(resultado_global="parcialmente_procedente", resultado_pedido="deferido", grau=None),
    ),
    (
        "Homologo o acordo celebrado entre as partes e extingo o feito com "
        "resolucao do merito.",
        "insalubridade",
        dict(resultado_global="acordo", resultado_pedido="nao_mencionado", grau=None),
    ),
    (
        "Ante o exposto, julgo PROCEDENTE o pedido e condeno a reclamada ao "
        "pagamento do adicional de insalubridade em grau maximo.",
        "insalubridade",
        dict(resultado_global="procedente", resultado_pedido="deferido", grau=40),
    ),
    (
        "Diante do exposto, extingo o processo sem resolucao do merito, na forma "
        "do art. 485, VI, do CPC.",
        "horas_extras",
        dict(resultado_global="extinto_sem_merito", resultado_pedido="nao_mencionado", grau=None),
    ),
    # --- lista longa: o verbo regente fica muito antes do item do tema -------
    (
        "Ante o exposto, julgo PROCEDENTES EM PARTE os pedidos para condenar a "
        "reclamada ao pagamento das seguintes verbas:\n"
        "a) aviso previo indenizado\nb) 13o salario proporcional\n"
        "c) ferias proporcionais acrescidas de 1/3\nd) FGTS do periodo\n"
        "e) multa do art. 477 da CLT\nf) multa do art. 467 da CLT\n"
        "g) horas extras excedentes da 8a diaria\nh) intervalo intrajornada\n"
        "i) adicional noturno\n"
        "j) adicional de insalubridade em grau medio, no percentual de 20% "
        "sobre o salario minimo, por todo o contrato",
        "insalubridade",
        dict(resultado_global="parcialmente_procedente", resultado_pedido="deferido", grau=20),
    ),
    # --- citacao de precedente nao decide o pedido ---------------------------
    (
        "Ante o exposto, julgo IMPROCEDENTES os pedidos, observados os "
        "parametros definidos pelo Supremo Tribunal Federal acerca da materia "
        "(adicional de insalubridade) no julgamento da ADI 6021.",
        "insalubridade",
        dict(resultado_global="improcedente", resultado_pedido="indeferido", grau=None),
    ),
    # --- desistencia homologada: nao houve julgamento de merito do pedido ----
    (
        "Isto posto, decido homologar a desistencia do pedido de adicional de "
        "insalubridade e extinguir o feito sem resolucao do merito em relacao a "
        "esse pleito, nos termos do art. 485, VIII, do CPC.",
        "insalubridade",
        dict(resultado_global="extinto_sem_merito", resultado_pedido="nao_analisado", grau=None),
    ),
    # --- tema so como base de reflexo de OUTRA verba -------------------------
    (
        "Isto posto, julgo PROCEDENTE EM PARTE para condenar a reclamada a "
        "pagar as diferencas da gratificacao a ser incorporada, bem como dos "
        "reflexos sobre FGTS, 13o salarios, ferias + 1/3, anuenio, adicionais "
        "de insalubridade ou periculosidade, adicional noturno e horas extras.",
        "insalubridade",
        dict(resultado_global="parcialmente_procedente",
             resultado_pedido="nao_mencionado", grau=None),
    ),
    # --- extincao sem merito DO PEDIDO --------------------------------------
    (
        "Isto posto, decido acolher a inepcia do pedido de pagamento de "
        "adicional de insalubridade, extinguindo-o sem resolucao do merito, e "
        "julgar PROCEDENTE EM PARTE os demais pedidos.",
        "insalubridade",
        dict(resultado_global="parcialmente_procedente",
             resultado_pedido="nao_analisado", grau=None),
    ),
    # --- extinguir os REFLEXOS nao extingue o adicional ----------------------
    (
        "Isto posto, acolho de oficio a preliminar de inepcia para extinguir, "
        "sem resolucao de merito, a pretensao de pagamento dos reflexos do "
        "adicional de insalubridade; no merito, julgo PROCEDENTE EM PARTE para "
        "condenar a reclamada ao pagamento do adicional de insalubridade em "
        "grau medio (20%).",
        "insalubridade",
        dict(resultado_global="parcialmente_procedente",
             resultado_pedido="deferido", grau=20),
    ),
    # --- parcial sem nomear o pedido: decide o fecho do capitulo -------------
    (
        "Ante o exposto, julgo PARCIALMENTE PROCEDENTES os pedidos para condenar "
        "a reclamada ao pagamento de horas extras e reflexos. Custas pela "
        "reclamada.",
        "insalubridade",
        dict(resultado_global="parcialmente_procedente", resultado_pedido="indeferido", grau=None),
    ),
]

# fundamentacao usada apenas pelo ultimo caso; os demais rodam sem ela
FUNDAMENTACOES = {
    len(CASOS) - 1: (
        "DO ADICIONAL DE INSALUBRIDADE\n"
        "O laudo pericial concluiu pela ausencia de agente insalubre acima dos "
        "limites de tolerancia da NR-15. Pelo exposto, indefiro o adicional de "
        "insalubridade e seus reflexos."
    ),
}


# Casos que dependem das regras de coerencia da versao 2.0 (indice 0-based em
# CASOS). Sao testados SEMPRE, com a correcao ligada a forca: manter a versao
# 1.0 ativa nao pode significar deixar de exercitar a regra.
CASOS_SO_NA_V2 = {10, 11}


def _testes():
    global CORRIGE_COERENCIA
    original = CORRIGE_COERENCIA
    falhas = 0
    print(f"versao do dataset ativa: {VERSAO_DATASET}"
          f"{'' if CORRIGE_COERENCIA else '  (regras de coerencia desligadas)'}\n")
    for i, (disp, tema, esperado) in enumerate(CASOS, 1):
        CORRIGE_COERENCIA = True if (i - 1) in CASOS_SO_NA_V2 else original
        try:
            r = rotular(disp, tema, FUNDAMENTACOES.get(i - 1, ""))
        finally:
            CORRIGE_COERENCIA = original
        obtido = dict(resultado_global=r.resultado_global,
                      resultado_pedido=r.resultado_pedido,
                      grau=r.grau)
        ok = obtido == esperado
        falhas += 0 if ok else 1
        marca = "  [regra da v2.0]" if (i - 1) in CASOS_SO_NA_V2 else ""
        print(f"[{'OK ' if ok else 'ERRO'}] caso {i} ({tema}){marca}")
        print(f"       {obtido}")
        if not ok:
            print(f"       esperado: {esperado}")
    print(f"\n{len(CASOS) - falhas}/{len(CASOS)} casos corretos.")
    return falhas


if __name__ == "__main__":
    raise SystemExit(1 if _testes() else 0)