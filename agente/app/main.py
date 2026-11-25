"""Serviço do agente do JuriPredict: API interna, sem tela, chamada pelo backend Django."""

import uvicorn
from fastapi import FastAPI

from app.api.v1.router import router as api_router
from app.core.config import APP_NAME, DESCRIPTION, HOST, PORT, VERSION

app = FastAPI(title=APP_NAME, description=DESCRIPTION, version=VERSION)
app.include_router(api_router)


@app.get("/health", tags=["Infraestrutura"])
async def health() -> dict:
    return {"status": "ok", "service": "agente-juripredict", "version": VERSION}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=HOST, port=PORT)
