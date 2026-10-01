from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from organizations.context import EscritorioContextMixin
from organizations.permissions import PodeLerAuditoria, TemContextoEscritorio

from .models import EventoAuditoria
from .serializers import EventoAuditoriaSerializer


class EventoAuditoriaViewSet(EscritorioContextMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = EventoAuditoriaSerializer
    permission_classes = (IsAuthenticated, TemContextoEscritorio, PodeLerAuditoria)

    def get_queryset(self):
        return EventoAuditoria.objects.filter(
            escritorio=self.get_escritorio()
        ).select_related("ator")

