import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.config import AGENTE_SEGREDO

from .endpoints.analista import router as analista_router


def require_backend(authorization: Annotated[str, Header()] = "") -> None:
    """Só o backend do JuriPredict chama o agente. Sem segredo configurado, recusa tudo."""
    if not AGENTE_SEGREDO:
        raise HTTPException(503, "O segredo do agente não está configurado no serviço.")
    if not hmac.compare_digest(authorization.encode(), f"Bearer {AGENTE_SEGREDO}".encode()):
        raise HTTPException(401, "Credencial do agente ausente ou inválida.")


router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_backend)])
router.include_router(analista_router)
