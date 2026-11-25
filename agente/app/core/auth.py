"""Porta de entrada: só o backend do JuriPredict, que conhece o segredo, passa daqui."""

import hmac

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from app.core.config import AGENTE_SEGREDO


class RequireBackend:
    """Confere o segredo antes de ler o corpo, porque a URL é pública no Render.

    ASGI puro, e não uma dependência do FastAPI: a dependência só roda com o corpo já lido.
    Tudo é negado por padrão, menos o `/health`; sem segredo configurado, nada entra.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "lifespan" and scope["path"] != "/health":
            refusal = self._refusal(Headers(scope=scope).get("authorization", ""))
            if refusal:
                status, detail = refusal
                await JSONResponse({"detail": detail}, status)(scope, receive, send)
                return
        await self.app(scope, receive, send)

    @staticmethod
    def _refusal(authorization: str) -> tuple[int, str] | None:
        if not AGENTE_SEGREDO:
            return 503, "O segredo do agente não está configurado no serviço."
        if not hmac.compare_digest(authorization.encode(), f"Bearer {AGENTE_SEGREDO}".encode()):
            return 401, "Credencial do agente ausente ou inválida."
        return None
