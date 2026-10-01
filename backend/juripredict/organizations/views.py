from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .context import EscritorioContextMixin
from .models import Escritorio, MembroEscritorio
from .permissions import PodeGerenciarEscritorio, TemContextoEscritorio
from .selectors import memberships_do_usuario
from .serializers import EscritorioSerializer, MembroEscritorioSerializer
from .services import atualizar_escritorio, atualizar_membro


class EscritorioViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    EscritorioContextMixin,
    viewsets.GenericViewSet,
):
    serializer_class = EscritorioSerializer
    http_method_names = ("get", "patch", "head", "options")

    def get_permissions(self):
        classes = [IsAuthenticated]
        if self.action != "list":
            classes.extend([TemContextoEscritorio, PodeGerenciarEscritorio])
        return [permission() for permission in classes]

    def get_queryset(self):
        if self.action == "list":
            return Escritorio.objects.filter(
                membros__in=memberships_do_usuario(self.request.user)
            ).distinct()
        return Escritorio.objects.filter(pk=self.get_escritorio().pk)

    def perform_update(self, serializer):
        escritorio = atualizar_escritorio(
            escritorio=serializer.instance,
            membro_ator=self.get_membro_escritorio(),
            dados=serializer.validated_data,
        )
        serializer.instance = escritorio


class MembroEscritorioViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    EscritorioContextMixin,
    viewsets.GenericViewSet,
):
    serializer_class = MembroEscritorioSerializer
    permission_classes = (IsAuthenticated, TemContextoEscritorio, PodeGerenciarEscritorio)
    http_method_names = ("get", "patch", "head", "options")

    def get_queryset(self):
        escritorio = self.get_escritorio()
        if str(escritorio.pk) != str(self.kwargs["escritorio_id"]):
            return MembroEscritorio.objects.none()
        return MembroEscritorio.objects.filter(escritorio=escritorio).select_related(
            "usuario", "escritorio"
        )

    def perform_update(self, serializer):
        membro = atualizar_membro(
            membro=serializer.instance,
            membro_ator=self.get_membro_escritorio(),
            papel=serializer.validated_data.get("papel"),
            status=serializer.validated_data.get("status"),
        )
        serializer.instance = membro

