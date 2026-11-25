"""Grafo pequeno e auditável do analista: preparar → buscar casos → analisar → medir."""

from langgraph.graph import END, START, StateGraph

from app.core.llm import langfuse_callbacks

from .nodes import analyze_case, measure_case, prepare_context, retrieve_cases
from .schema import CaseRequest
from .state import AnalistaState


def build_graph():
    graph = StateGraph(AnalistaState)
    graph.add_node("prepare_context", prepare_context)
    graph.add_node("retrieve_cases", retrieve_cases)
    graph.add_node("analyze_case", analyze_case)
    graph.add_node("measure_case", measure_case)
    graph.add_edge(START, "prepare_context")
    graph.add_edge("prepare_context", "retrieve_cases")
    graph.add_edge("retrieve_cases", "analyze_case")
    graph.add_edge("analyze_case", "measure_case")
    graph.add_edge("measure_case", END)
    return graph.compile(name="analista")


analista_graph = build_graph()


def analyze(request: CaseRequest, on_step=None) -> AnalistaState:
    """Roda o grafo. `on_step(nó)` é chamado ao fim de cada nó, para o polling mostrar
    o progresso."""
    state: AnalistaState = {}
    for update in analista_graph.stream(
        {"request": request},
        config={"callbacks": langfuse_callbacks(), "run_name": "analista"},
        stream_mode="updates",
    ):
        for node, node_state in update.items():
            state = node_state  # cada nó devolve o estado completo
            if on_step:
                on_step(node)
    return state
