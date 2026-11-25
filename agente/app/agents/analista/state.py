"""Estado interno do grafo do analista."""

from typing import TypedDict

from app.core.vector_store import RetrievedCase

from .schema import AnalysisDraft, CaseMeasurement, CaseRequest, CriteriaCatalog


class AnalistaState(TypedDict, total=False):
    request: CaseRequest
    assumptions: list[str]
    catalog: CriteriaCatalog
    cases: list[RetrievedCase]
    analysis: AnalysisDraft
    measurement: CaseMeasurement
