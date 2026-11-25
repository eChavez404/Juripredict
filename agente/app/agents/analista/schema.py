"""Contratos do agente analista.

O modelo avalia o caso só pelos critérios do catálogo fechado e versionado em
`app/prompts/analista/criterios/` e só cita casos trazidos da base vetorial. Pesos e
fundamentos ficam nesses arquivos, para revisão humana, e não no prompt; a medida é
calculada em código.
"""

from enum import StrEnum
from typing import Annotated, Literal

import yaml
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.privacy import mask_documents
from app.prompts import PROMPTS_DIR

CATALOG_DIR = PROMPTS_DIR / "analista" / "criterios"


class LabeledEnum(StrEnum):
    """StrEnum com rótulo para o formulário: `MEMBRO = "valor", "Rótulo"`."""

    label: str

    def __new__(cls, value: str, label: str):
        member = str.__new__(cls, value)
        member._value_ = value
        member.label = label
        return member


class Theme(LabeledEnum):
    INSALUBRIDADE = "insalubridade", "Adicional de insalubridade"
    PERICULOSIDADE = "periculosidade", "Adicional de periculosidade"


class Stage(LabeledEnum):
    """Fases em ordem cronológica: a ordem define o que ainda dá para corrigir."""

    PRE_PROCESSUAL = "pre_processual", "Antes de ajuizar"
    INICIAL = "inicial", "Inicial apresentada, sem defesa"
    INSTRUCAO = "instrucao", "Em instrução"
    SENTENCA = "sentenca", "Aguardando ou com sentença"
    RECURSO = "recurso", "Em recurso"

    @property
    def rank(self) -> int:
        return list(Stage).index(self)


class Evidence(LabeledEnum):
    LAUDO_PERICIAL = "laudo_pericial", "Laudo pericial do processo"
    PROVA_EMPRESTADA = "prova_emprestada", "Laudo de outro processo"
    LTCAT = "ltcat", "LTCAT"
    PPP = "ppp", "PPP"
    PGR_PPRA = "pgr_ppra", "PGR / PPRA"
    FICHA_EPI = "ficha_epi", "Fichas de EPI"
    TESTEMUNHAS = "testemunhas", "Testemunhas"
    FOTOS_VIDEOS = "fotos_videos", "Fotos ou vídeos"
    CONTRACHEQUES = "contracheques", "Contracheques"


class Status(StrEnum):
    ATENDIDO = "atendido"
    PARCIAL = "parcial"
    AUSENTE = "ausente"
    NAO_APLICAVEL = "nao_aplicavel"


# --- Catálogo fechado ---------------------------------------------------------

CatalogId = Annotated[str, Field(pattern=r"^[a-z0-9_]+$")]


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: CatalogId
    nome: str
    descricao: str
    peso: int = Field(ge=1, le=5)
    # Última fase em que a falha ainda pode ser corrigida.
    sanavel_ate: Stage
    fundamentos: list[str] = Field(min_length=1)

    def fixable_at(self, fase: Stage) -> bool:
        return fase.rank <= self.sanavel_ate.rank


class CriteriaCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tema: Theme
    versao: str
    criterios: list[Criterion] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [c.id for c in self.criterios]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.tema}: id de critério duplicado")
        return self


def _load_catalogs() -> dict[Theme, CriteriaCatalog]:
    catalogs: dict[Theme, CriteriaCatalog] = {}
    for path in sorted(CATALOG_DIR.glob("*.yaml")):
        catalog = CriteriaCatalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if catalog.tema in catalogs:
            raise ValueError(f"tema duplicado no catálogo: {catalog.tema}")
        catalogs[catalog.tema] = catalog
    return catalogs


CATALOGOS = _load_catalogs()


# --- Contratos do agente ------------------------------------------------------

# Mascarado na borda: o relato cru nunca chega ao grafo, ao modelo nem ao Langfuse.
MaskedText = Annotated[str, AfterValidator(mask_documents)]


class CaseRequest(BaseModel):
    """Dados do caso informados no formulário."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tema: Theme
    fase: Stage
    relato: MaskedText = Field(min_length=40, max_length=12000)
    provas: list[Evidence] = Field(default_factory=list, max_length=len(Evidence))
    orgao_julgador: MaskedText | None = Field(default=None, max_length=200)
    duvida: MaskedText | None = Field(default=None, max_length=500)


class CriterionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterio_id: str = Field(description="id exato de um dos CRITERIOS_DO_TEMA")
    situacao: Status
    evidencia: str = Field(
        min_length=3, max_length=500, description="O que no relato ou nas provas sustenta isso"
    )


class Improvement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterio_id: str = Field(description="id exato do critério que a ação melhora")
    acao: str = Field(min_length=10, max_length=500)
    justificativa: str = Field(min_length=10, max_length=500)
    caso_ids: list[str] = Field(
        default_factory=list, max_length=5, description="ids de CASOS_PROXIMOS que apoiam a ação"
    )


class CaseComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caso_id: str = Field(description="id exato de um dos CASOS_PROXIMOS")
    semelhancas: str = Field(min_length=3, max_length=600)
    diferencas: str = Field(min_length=3, max_length=600)


class AnalysisDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str = Field(min_length=3, max_length=120)
    resumo: str = Field(min_length=10, max_length=1200)
    criterios: list[CriterionAssessment] = Field(min_length=1, max_length=20)
    melhorias: list[Improvement] = Field(max_length=12)
    casos_proximos: list[CaseComparison] = Field(max_length=5)
    riscos: list[str] = Field(max_length=8)


class CaseMeasurement(BaseModel):
    """Quanto do que o tema exige está demonstrado. Não é probabilidade de êxito."""

    indice_atual: int = Field(ge=0, le=100)
    indice_potencial: int = Field(ge=0, le=100)
    ganho: int = Field(ge=0, le=100)
    alertas: list[str] = Field(default_factory=list)
    pontos_fortes: list[str] = Field(default_factory=list)


class SimilarCase(BaseModel):
    """Caso exibido. Sem o texto da decisão, que pode trazer nomes das partes."""

    id_sentenca: str
    numero_cnj: str | None
    tipo_documento: str | None
    orgao_julgador: str | None
    data_julgamento: str | None
    resultado: str | None
    similaridade: float


class AnalysisResponse(BaseModel):
    analise: AnalysisDraft
    catalogo: CriteriaCatalog
    medicao: CaseMeasurement
    casos: list[SimilarCase]
    suposicoes: list[str]
    disclaimer: str


class AnalysisJob(BaseModel):
    """Análise em andamento, consultada por polling."""

    job_id: str
    status: Literal["running", "done", "error"]
    step: str | None = None
    result: AnalysisResponse | None = None
    error: str | None = None


class Option(BaseModel):
    value: str
    label: str


class OptionsResponse(BaseModel):
    temas: list[Option]
    fases: list[Option]
    provas: list[Option]
