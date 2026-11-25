"""Nós do analista: preparar o contexto, buscar casos, analisar e medir."""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.core import vector_store
from app.core.input_errors import NoCriteriaAvailable
from app.core.llm import invoke_with_timeout_translation, model
from app.core.privacy import mask_documents
from app.core.structured_output import (
    STRUCTURED_OUTPUT_RETRY_ERRORS,
    StructuredOutputError,
)
from app.prompts import load_prompt

from .schema import CATALOGOS, AnalysisDraft, CaseMeasurement, Status
from .state import AnalistaState

SYSTEM_PROMPT = load_prompt("analista/system.md")

MAX_CASOS = 5
# TODO(revisão): crédito de cada situação no índice.
CREDITO = {Status.ATENDIDO: 1.0, Status.PARCIAL: 0.5, Status.AUSENTE: 0.0}


def prepare_context(state: AnalistaState) -> AnalistaState:
    """Escolhe o catálogo do tema e registra as suposições. Nunca pergunta ao usuário."""
    request = state["request"]
    catalog = CATALOGOS.get(request.tema)
    if catalog is None:
        raise NoCriteriaAvailable()
    assumptions = ["Análise feita pela ótica de quem pede o adicional (reclamante)."]
    provas = list(dict.fromkeys(request.provas))
    if not provas:
        assumptions.append("Nenhuma prova informada: considerado que ainda não há prova nos autos.")
    if not request.orgao_julgador:
        assumptions.append("Órgão julgador não informado: não influencia a busca de casos.")
    return {
        **state,
        "request": request.model_copy(update={"provas": provas}),
        "assumptions": assumptions,
        "catalog": catalog,
    }


def retrieve_cases(state: AnalistaState) -> AnalistaState:
    """Busca os casos mais próximos. Sem base configurada, segue e avisa."""
    request = state["request"]
    cases = []
    assumptions = list(state["assumptions"])
    if not vector_store.is_configured():
        assumptions.append("Base de casos não configurada: nenhum caso próximo foi consultado.")
    else:
        parts = [request.tema.label, request.orgao_julgador, request.relato]
        query = "\n".join(filter(None, parts))
        cases = vector_store.search_cases(query, tema=request.tema.value, limit=MAX_CASOS)
        if not cases:
            assumptions.append("A base de casos não devolveu nenhum caso para esse tema.")
    return {**state, "cases": cases, "assumptions": assumptions}


def _validate_against_context(state: AnalistaState, analysis: AnalysisDraft) -> None:
    expected = sorted(c.id for c in state["catalog"].criterios)
    if sorted(item.criterio_id for item in analysis.criterios) != expected:
        raise ValueError("A análise não avaliou cada critério do tema exatamente uma vez.")
    if all(item.situacao is Status.NAO_APLICAVEL for item in analysis.criterios):
        raise ValueError("A análise descartou todos os critérios do tema.")
    open_ids = {
        item.criterio_id
        for item in analysis.criterios
        if item.situacao in (Status.PARCIAL, Status.AUSENTE)
    }
    if any(item.criterio_id not in open_ids for item in analysis.melhorias):
        raise ValueError("Há melhoria para critério que não está parcial ou ausente.")
    compared = [item.caso_id for item in analysis.casos_proximos]
    if len(compared) != len(set(compared)):
        raise ValueError("A análise repetiu um caso.")
    cited = {*compared, *(case_id for item in analysis.melhorias for case_id in item.caso_ids)}
    if not cited <= {case.id_sentenca for case in state["cases"]}:
        raise ValueError("A análise citou caso fora dos trazidos da base.")


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _untrusted(tag: str, value) -> str:
    """Bloco de dados. O `<` vira escape JSON, para o conteúdo não conseguir fechar a tag."""
    content = _compact(value).replace("<", "\\u003c")
    return f"<{tag}>\n{content}\n</{tag}>"


def analyze_case(state: AnalistaState) -> AnalistaState:
    request = state["request"]
    criteria = [
        {
            **criterion.model_dump(mode="json", exclude={"peso"}),
            "sanavel_na_fase_atual": criterion.fixable_at(request.fase),
        }
        for criterion in state["catalog"].criterios
    ]
    cases = [
        {
            "id": case.id_sentenca,
            "tipo": case.tipo_documento,
            "orgao_julgador": case.orgao_julgador,
            "data_julgamento": case.data_julgamento,
            "resultado": case.resultado,
            "trecho": mask_documents(case.texto),
        }
        for case in state["cases"]
    ]
    prompt = (
        f"CRITERIOS_DO_TEMA:\n{_compact(criteria)}\n\n"
        f"SUPOSICOES_REGISTRADAS:\n{_compact(state['assumptions'])}\n\n"
        f"{_untrusted('CASOS_PROXIMOS', cases)}\n\n"
        f"{_untrusted('CONTEXTO_NAO_CONFIAVEL', request.model_dump(mode='json'))}\n\n"
        "Analise o caso completo."
    )
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
    # json_schema = structured output nativo do Gemini.
    structured_model = model().with_structured_output(AnalysisDraft, method="json_schema")
    for attempt in range(2):
        attempt_messages = messages
        if attempt:
            attempt_messages = [
                *messages,
                HumanMessage(
                    content=(
                        "A resposta anterior violou o contrato. Analise novamente, avaliando cada "
                        "critério do tema exatamente uma vez, propondo melhorias só para critérios "
                        "parciais ou ausentes e citando somente ids de CASOS_PROXIMOS."
                    )
                ),
            ]
        try:
            result = invoke_with_timeout_translation(structured_model, attempt_messages)
            analysis = (
                result
                if isinstance(result, AnalysisDraft)
                else AnalysisDraft.model_validate(result)
            )
            _validate_against_context(state, analysis)
            return {**state, "analysis": analysis}
        except STRUCTURED_OUTPUT_RETRY_ERRORS as error:
            if attempt:
                raise StructuredOutputError(
                    "A IA não conseguiu devolver uma análise válida. Tente novamente."
                ) from error
    raise AssertionError("Fluxo de análise encerrado sem resultado.")


def measure_case(state: AnalistaState) -> AnalistaState:
    """Calcula o índice atual e o potencial, sem IA.

    O potencial considera atendidos os critérios em aberto que têm melhoria proposta e
    ainda podem ser corrigidos na fase atual.
    """
    request = state["request"]
    analysis = state["analysis"]
    status = {item.criterio_id: item.situacao for item in analysis.criterios}
    with_improvement = {item.criterio_id for item in analysis.melhorias}
    alertas: list[str] = []
    pontos_fortes: list[str] = []

    total = current = potential = 0.0
    for criterion in state["catalog"].criterios:
        situacao = status[criterion.id]
        if situacao is Status.NAO_APLICAVEL:
            continue
        credit = CREDITO[situacao]
        fixable = criterion.fixable_at(request.fase)
        improvable = fixable and criterion.id in with_improvement
        total += criterion.peso
        current += criterion.peso * credit
        potential += criterion.peso * (1.0 if improvable else credit)
        if situacao is Status.ATENDIDO:
            pontos_fortes.append(criterion.nome)
        elif not fixable:
            alertas.append(f"Não é mais possível corrigir na fase atual: {criterion.nome}.")
        elif not improvable:
            alertas.append(f"Em aberto e sem melhoria proposta: {criterion.nome}.")

    if not state["cases"]:
        alertas.append("Análise sem casos próximos: baseada só nos critérios do tema.")

    indice_atual = round(100 * current / total)
    indice_potencial = round(100 * potential / total)
    return {
        **state,
        "measurement": CaseMeasurement(
            indice_atual=indice_atual,
            indice_potencial=indice_potencial,
            ganho=indice_potencial - indice_atual,
            alertas=alertas,
            pontos_fortes=pontos_fortes,
        ),
    }
