from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import BaseThrottle, ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from api.serializers import UsuarioSerializer
from config.openapi import DetalheSerializer, SessaoSerializer, TokenApiCriadoSerializer

from .serializers import (
    AceitarConviteSerializer,
    ConfirmarEmailSerializer,
    ConfirmarResetSenhaSerializer,
    CriarTokenApiSerializer,
    ExcluirContaSerializer,
    LogoutSerializer,
    RegistroSerializer,
    SolicitarResetSenhaSerializer,
    TokenApiSerializer,
)
from .tokens_api import criar_token_api, revogar_token_api, tokens_do_usuario
from .services import (
    aceitar_convite,
    confirmar_email,
    confirmar_reset_senha,
    enviar_verificacao,
    excluir_conta,
    exportar_dados,
    registrar_conta,
    solicitar_reset_senha,
)


def _ip(request):
    """IP do cliente, respeitando NUM_PROXIES (o mesmo critério do throttle)."""
    return BaseThrottle().get_ident(request) or None


def _sessao(usuario):
    """Mesmo formato da resposta de login, para o app entrar direto."""
    refresh = RefreshToken.for_user(usuario)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": UsuarioSerializer(usuario).data,
    }


class _EndpointPublico(APIView):
    """Endpoint sem login. O limite de requisições é por escopo, não o global."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]


class RegistroAPIView(_EndpointPublico):
    throttle_scope = "registro"

    @extend_schema(request=RegistroSerializer, responses={201: SessaoSerializer})
    def post(self, request):
        serializer = RegistroSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        usuario = registrar_conta(
            nome=dados["nome"],
            email=dados["email"],
            senha=dados["senha"],
            escritorio_nome=dados["escritorio_nome"],
            ip=_ip(request),
        )
        return Response(_sessao(usuario), status=status.HTTP_201_CREATED)


class AceitarConviteAPIView(_EndpointPublico):
    throttle_scope = "convite"

    @extend_schema(request=AceitarConviteSerializer, responses={201: SessaoSerializer})
    def post(self, request):
        serializer = AceitarConviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        usuario = aceitar_convite(
            token=dados["token"],
            senha=dados["senha"],
            nome=dados.get("nome", ""),
            aceite_termos=dados["aceite_termos"],
            ip=_ip(request),
        )
        return Response(_sessao(usuario), status=status.HTTP_201_CREATED)


class SolicitarResetSenhaAPIView(_EndpointPublico):
    throttle_scope = "recuperacao_senha"

    @extend_schema(request=SolicitarResetSenhaSerializer, responses=DetalheSerializer)
    def post(self, request):
        serializer = SolicitarResetSenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        solicitar_reset_senha(email=serializer.validated_data["email"])
        # Resposta idêntica exista ou não a conta: não revela quem é cliente.
        return Response(
            {"detail": "Se o e-mail estiver cadastrado, você receberá as instruções."}
        )


class ConfirmarResetSenhaAPIView(_EndpointPublico):
    throttle_scope = "recuperacao_senha"

    @extend_schema(request=ConfirmarResetSenhaSerializer, responses=DetalheSerializer)
    def post(self, request):
        serializer = ConfirmarResetSenhaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirmar_reset_senha(**serializer.validated_data)
        return Response({"detail": "Senha redefinida com sucesso."})


class LogoutAPIView(_EndpointPublico):
    """Revoga o refresh token no servidor.

    Não exige access token: quem sai por ele ter expirado também precisa
    conseguir encerrar a sessão. Resposta igual para token válido ou não.
    """

    throttle_scope = "refresh"

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass  # já inválido, expirado ou revogado: o objetivo está cumprido
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExportarDadosAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: {"type": "object", "description": "Cópia dos dados do titular."}})
    def get(self, request):
        resposta = Response(exportar_dados(usuario=request.user))
        resposta["Content-Disposition"] = 'attachment; filename="meus-dados-juripredict.json"'
        return resposta


class ExcluirContaAPIView(APIView):
    permission_classes = [IsAuthenticated]
    # pede a senha: quem tem um token roubado não deve poder testar senhas aqui
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conta_sensivel"

    @extend_schema(request=ExcluirContaSerializer, responses={204: None})
    def post(self, request):
        serializer = ExcluirContaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        excluir_conta(usuario=request.user, senha=serializer.validated_data["senha"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConfirmarEmailAPIView(_EndpointPublico):
    throttle_scope = "recuperacao_senha"

    @extend_schema(request=ConfirmarEmailSerializer, responses=DetalheSerializer)
    def post(self, request):
        serializer = ConfirmarEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirmar_email(token=serializer.validated_data["token"])
        return Response({"detail": "E-mail confirmado."})


class ReenviarVerificacaoAPIView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conta_sensivel"

    @extend_schema(request=None, responses=DetalheSerializer)
    def post(self, request):
        enviar_verificacao(request.user)
        return Response({"detail": "Se o e-mail ainda não estiver confirmado, enviamos um novo link."})


class _SomenteJwt(APIView):
    """Gerenciar tokens exige uma sessão de pessoa: um token de API nunca emite nem
    revoga tokens, nem os lista."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conta_sensivel"


class TokensApiAPIView(_SomenteJwt):
    @extend_schema(responses=TokenApiSerializer(many=True))
    def get(self, request):
        return Response(TokenApiSerializer(tokens_do_usuario(request.user), many=True).data)

    @extend_schema(request=CriarTokenApiSerializer, responses={201: TokenApiCriadoSerializer})
    def post(self, request):
        serializer = CriarTokenApiSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        token, texto = criar_token_api(
            usuario=request.user,
            nome=dados["nome"],
            senha=dados["senha"],
            validade_dias=dados.get("validade_dias"),
        )
        # O texto do token só aparece aqui; depois só o prefixo.
        return Response(
            {**TokenApiSerializer(token).data, "token": texto}, status=status.HTTP_201_CREATED
        )


class TokenApiDetalheAPIView(_SomenteJwt):
    @extend_schema(responses={204: None})
    def delete(self, request, token_id):
        revogar_token_api(usuario=request.user, token_id=token_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
