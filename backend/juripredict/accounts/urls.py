from django.urls import path

from .views import (
    AceitarConviteAPIView,
    ConfirmarEmailAPIView,
    ConfirmarResetSenhaAPIView,
    ExcluirContaAPIView,
    ExportarDadosAPIView,
    LogoutAPIView,
    RegistroAPIView,
    ReenviarVerificacaoAPIView,
    SolicitarResetSenhaAPIView,
    TokenApiDetalheAPIView,
    TokensApiAPIView,
)

urlpatterns = [
    path("auth/logout/", LogoutAPIView.as_view(), name="logout"),
    path("auth/tokens/", TokensApiAPIView.as_view(), name="tokens-api"),
    path(
        "auth/tokens/<int:token_id>/",
        TokenApiDetalheAPIView.as_view(),
        name="token-api-detalhe",
    ),
    path("auth/me/exportar/", ExportarDadosAPIView.as_view(), name="exportar-dados"),
    path("auth/me/excluir/", ExcluirContaAPIView.as_view(), name="excluir-conta"),
    path("auth/email/confirmar/", ConfirmarEmailAPIView.as_view(), name="email-confirmar"),
    path(
        "auth/email/reenviar/",
        ReenviarVerificacaoAPIView.as_view(),
        name="email-reenviar",
    ),
    path("auth/register/", RegistroAPIView.as_view(), name="registro"),
    path("auth/convites/aceitar/", AceitarConviteAPIView.as_view(), name="convite-aceitar"),
    path(
        "auth/password/reset/",
        SolicitarResetSenhaAPIView.as_view(),
        name="reset-senha-solicitar",
    ),
    path(
        "auth/password/reset/confirm/",
        ConfirmarResetSenhaAPIView.as_view(),
        name="reset-senha-confirmar",
    ),
]
