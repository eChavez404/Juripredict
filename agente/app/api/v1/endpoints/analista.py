"""Endpoints do analista: opções do formulário e análise do caso por polling.

`POST /analyses` só inicia a análise e devolve um `job_id`; o backend consulta
`GET /analyses/{job_id}` até o status virar `done` ou `error`.
"""

from enum import Enum
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.agents.analista import (
    AnalysisJob,
    AnalysisResponse,
    CaseRequest,
    OptionsResponse,
    analyze,
)
from app.agents.analista.schema import Evidence, Option, SimilarCase, Stage, Theme
from app.core import vector_store
from app.core.api_errors import analysis_error
from app.core.config import GOOGLE_API_KEY

router = APIRouter(tags=["Analista"])

DISCLAIMER = (
    "Esta análise apoia o trabalho do advogado e não substitui a avaliação profissional. "
    "O índice mede o quanto do que o tema exige está demonstrado; não é probabilidade de êxito. "
    "Confira cada fundamento e cada decisão na fonte antes de usar."
)
STEPS = ("prepare_context", "retrieve_cases", "analyze_case", "measure_case")

# ponytail: jobs em memória de um único processo; somem no restart e não funcionam
# com vários workers. Trocar por Redis ou banco quando escalar.
JOBS: dict[str, AnalysisJob] = {}
MAX_JOBS = 500


def _options(enum: type[Enum]) -> list[Option]:
    return [Option(value=member.value, label=member.label) for member in enum]


@router.get("/options", response_model=OptionsResponse)
def options():
    """Opções do formulário; a fonte da verdade são os enums do agente."""
    return OptionsResponse(
        ia_configurada=bool(GOOGLE_API_KEY),
        base_configurada=vector_store.is_configured(),
        temas=_options(Theme),
        fases=_options(Stage),
        provas=_options(Evidence),
    )


def _run_job(job: AnalysisJob, request: CaseRequest) -> None:
    def on_step(node: str) -> None:
        next_index = STEPS.index(node) + 1
        if next_index < len(STEPS):
            job.step = STEPS[next_index]

    try:
        state = analyze(request, on_step=on_step)
        job.result = AnalysisResponse(
            analise=state["analysis"],
            catalogo=state["catalog"],
            medicao=state["measurement"],
            casos=[
                SimilarCase.model_validate(case, from_attributes=True) for case in state["cases"]
            ],
            suposicoes=state["assumptions"],
            disclaimer=DISCLAIMER,
            aviso=state.get("aviso"),
        )
        job.status = "done"  # depois do result: o polling nunca vê "done" sem resultado
    except Exception as exc:  # noqa: BLE001 — a borda sanitiza qualquer falha do provedor
        job.error = analysis_error(exc, "analista").detail
        job.status = "error"


@router.post("/analyses", response_model=AnalysisJob, status_code=202)
def start_analysis(request: CaseRequest, background_tasks: BackgroundTasks):
    job = AnalysisJob(job_id=uuid4().hex, status="running", step=STEPS[0])
    JOBS[job.job_id] = job
    while len(JOBS) > MAX_JOBS:
        JOBS.pop(next(iter(JOBS)))
    background_tasks.add_task(_run_job, job, request)
    return job


@router.get("/analyses/{job_id}", response_model=AnalysisJob)
def get_analysis(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Análise não encontrada. Envie o caso de novo.")
    return job
