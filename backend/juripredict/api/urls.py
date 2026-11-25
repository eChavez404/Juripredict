from django.urls import include, path
from rest_framework.routers import DefaultRouter

from auditlog.views import EventoAuditoriaViewSet
from organizations.views import EscritorioViewSet

from .views import (
    AgenteAnaliseAPIView,
    AgenteAnalisesAPIView,
    AgenteOpcoesAPIView,
    AlterarSenhaAPIView,
    ClienteViewSet,
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    DashboardAPIView,
    EventoAgendaViewSet,
    JurimetriaAPIView,
    JurimetriaExportarAPIView,
    JurimetriaProcessosAPIView,
    JurimetriaTribunalAPIView,
    JurimetriaTribunalDecisoesAPIView,
    PendenciasAPIView,
    PrazoCalculoAPIView,
    ProcessoViewSet,
    UsuarioAtualAPIView,
)


router = DefaultRouter()
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("processos", ProcessoViewSet, basename="processo")
router.register("eventos", EventoAgendaViewSet, basename="evento")
router.register("escritorios", EscritorioViewSet, basename="escritorio")
router.register("auditoria", EventoAuditoriaViewSet, basename="auditoria")


urlpatterns = [
    path("auth/token/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("auth/me/", UsuarioAtualAPIView.as_view(), name="usuario-atual"),
    path("auth/password/", AlterarSenhaAPIView.as_view(), name="alterar-senha"),
    path("dashboard/", DashboardAPIView.as_view(), name="dashboard"),
    path("jurimetria/", JurimetriaAPIView.as_view(), name="jurimetria"),
    path("jurimetria/processos/", JurimetriaProcessosAPIView.as_view(), name="jurimetria-processos"),
    path("jurimetria/exportar/", JurimetriaExportarAPIView.as_view(), name="jurimetria-exportar"),
    path("jurimetria/tribunal/", JurimetriaTribunalAPIView.as_view(), name="jurimetria-tribunal"),
    path(
        "jurimetria/tribunal/decisoes/",
        JurimetriaTribunalDecisoesAPIView.as_view(),
        name="jurimetria-tribunal-decisoes",
    ),
    path("pendencias/", PendenciasAPIView.as_view(), name="pendencias"),
    path("prazos/calcular/", PrazoCalculoAPIView.as_view(), name="prazo-calcular"),
    path("agente/opcoes/", AgenteOpcoesAPIView.as_view(), name="agente-opcoes"),
    path("agente/analises/", AgenteAnalisesAPIView.as_view(), name="agente-analises"),
    path("agente/analises/<str:analise_id>/", AgenteAnaliseAPIView.as_view(), name="agente-analise"),
    path("", include("organizations.urls")),
    path("", include(router.urls)),
]
