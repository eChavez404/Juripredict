from fastapi import APIRouter

from .endpoints.analista import router as analista_router

router = APIRouter(prefix="/api/v1")
router.include_router(analista_router)
