"""Serviço do agente do JuriPredict: sem tela nem documentação pública, só para o backend."""

import uvicorn
from fastapi import FastAPI

from app.api.v1.router import router as api_router
from app.core.auth import RequireBackend
from app.core.config import APP_NAME, DESCRIPTION, HOST, PORT, VERSION

app = FastAPI(
    title=APP_NAME,
    description=DESCRIPTION,
    version=VERSION,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(RequireBackend)
app.include_router(api_router)


@app.get("/health", tags=["Infraestrutura"])
async def health() -> dict:
    return {"status": "ok", "service": "agente-juripredict", "version": VERSION}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT)
