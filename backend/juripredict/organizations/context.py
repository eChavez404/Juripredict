from rest_framework.exceptions import PermissionDenied

from .selectors import (
    ContextoEscritorioAusente,
    ContextoEscritorioInvalido,
    resolver_membership,
)


def contexto_escritorio_da_request(request, *, obrigatorio=True):
    if hasattr(request, "membro_escritorio"):
        membro = request.membro_escritorio
        if membro is None and obrigatorio:
            raise PermissionDenied("Um contexto de escritório ativo é obrigatório.")
        return membro

    try:
        membro = resolver_membership(
            request.user,
            request.headers.get("X-Escritorio-ID"),
            obrigatorio=obrigatorio,
        )
    except (ContextoEscritorioAusente, ContextoEscritorioInvalido) as exc:
        raise PermissionDenied(str(exc)) from exc

    request.membro_escritorio = membro
    request.escritorio = membro.escritorio if membro else None
    return membro


class EscritorioContextMixin:
    def get_membro_escritorio(self):
        return contexto_escritorio_da_request(self.request)

    def get_escritorio(self):
        return self.get_membro_escritorio().escritorio

