from rest_framework.permissions import BasePermission, SAFE_METHODS

from .capabilities import request_tem_capability
from .context import contexto_escritorio_da_request
from .models import MembroEscritorio


class TemContextoEscritorio(BasePermission):
    message = "Um contexto de escritório ativo é obrigatório."

    def has_permission(self, request, view):
        contexto_escritorio_da_request(request)
        return True


class PodeGerenciarEscritorio(BasePermission):
    message = "Somente proprietários e administradores podem realizar esta ação."

    def has_permission(self, request, view):
        membro = contexto_escritorio_da_request(request)
        if request.method in SAFE_METHODS:
            return True
        return membro.papel in {
            MembroEscritorio.Papel.OWNER,
            MembroEscritorio.Papel.ADMIN,
        }


class PodeLerAuditoria(BasePermission):
    message = "Somente proprietários e administradores podem consultar a auditoria."

    def has_permission(self, request, view):
        membro = contexto_escritorio_da_request(request)
        return membro.papel in {
            MembroEscritorio.Papel.OWNER,
            MembroEscritorio.Papel.ADMIN,
        }


def exige_capability(capability):
    """Fabrica uma permissão que só deixa passar quem tem a capability no escritório."""

    class TemCapability(BasePermission):
        message = "O seu papel neste escritório não permite esta ação."

        def has_permission(self, request, view):
            return request_tem_capability(request, capability)

    TemCapability.__name__ = f"TemCapability[{capability}]"
    return TemCapability
