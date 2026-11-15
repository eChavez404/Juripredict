"""Rotas do conector MCP remoto. A regra fica em ``accounts.oauth``; aqui só HTTP.

Dois grupos:

- protocolo OAuth (``/.well-known``, ``/oauth/...``): sem login de pessoa, o aplicativo
  se identifica no corpo ou no cabeçalho Basic; fora do OpenAPI do app;
- telas do app (``/api/v1/oauth/pedido/``, ``/api/v1/auth/conexoes/``): exigem a
  sessão da pessoa. Um token de API nunca autoriza nem revoga aplicativos.
"""

import base64
import hmac
from urllib.parse import unquote_plus, urlsplit

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from organizations.selectors import memberships_do_usuario

from . import oauth
from .serializers import (
    ConexaoOAuthSerializer,
    ConsentimentoOAuthSerializer,
    ErroPedidoOAuthSerializer,
    ParametrosPedidoOAuthSerializer,
    PedidoOAuthSerializer,
    RedirecionamentoOAuthSerializer,
)
from .views import _SomenteJwt


class _ProtocoloOAuth(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    parser_classes = [JSONParser, FormParser]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"  # RFC 6749, 5.1: token nenhum em cache
        return response

    def handle_exception(self, exc):
        if isinstance(exc, oauth.ErroOAuth):
            return Response(exc.corpo(), status=exc.status)
        return super().handle_exception(exc)


def _credenciais_do_cliente(request):
    """client_id e segredo, pelo cabeçalho Basic (RFC 6749, 2.3.1) ou pelo corpo."""
    cabecalho = request.headers.get("Authorization", "")
    if cabecalho[:6].lower() == "basic ":
        try:
            client_id, _, segredo = base64.b64decode(cabecalho[6:]).decode().partition(":")
        except (ValueError, UnicodeDecodeError) as exc:
            raise oauth.ErroOAuth("invalid_client", "Cabeçalho Basic inválido.", status=401) from exc
        return unquote_plus(client_id), unquote_plus(segredo)
    return request.data.get("client_id"), request.data.get("client_secret")


class MetadadosOAuthAPIView(_ProtocoloOAuth):
    throttle_classes = []

    @extend_schema(exclude=True)
    def get(self, request):
        return Response(oauth.metadados())


class RegistroClienteOAuthAPIView(_ProtocoloOAuth):
    throttle_scope = "oauth_registro"

    @extend_schema(exclude=True)
    def post(self, request):
        cliente, segredo = oauth.registrar_cliente(request.data)
        return Response(oauth.resposta_registro(cliente, segredo), status=status.HTTP_201_CREATED)


class TokenOAuthAPIView(_ProtocoloOAuth):
    throttle_scope = "oauth_token"

    @extend_schema(exclude=True)
    def post(self, request):
        cliente = oauth.autenticar_cliente(*_credenciais_do_cliente(request))
        tipo = request.data.get("grant_type")
        if tipo == "authorization_code":
            corpo = oauth.trocar_codigo(
                cliente=cliente,
                codigo=request.data.get("code"),
                redirect_uri=request.data.get("redirect_uri"),
                code_verifier=request.data.get("code_verifier"),
            )
        elif tipo == "refresh_token":
            corpo = oauth.renovar(cliente=cliente, renovacao=request.data.get("refresh_token"))
        else:
            raise oauth.ErroOAuth("unsupported_grant_type", "Use authorization_code ou refresh_token.")
        return Response(corpo)


class RevogarOAuthAPIView(_ProtocoloOAuth):
    throttle_scope = "oauth_token"

    @extend_schema(exclude=True)
    def post(self, request):
        cliente = oauth.autenticar_cliente(*_credenciais_do_cliente(request))
        oauth.revogar_token(cliente=cliente, texto=request.data.get("token"))
        return Response(status=status.HTTP_200_OK)  # RFC 7009: 200 até para token desconhecido


class IntrospeccaoOAuthAPIView(_ProtocoloOAuth):
    throttle_scope = "oauth_introspeccao"

    @extend_schema(exclude=True)
    def post(self, request):
        segredo = settings.OAUTH_SEGREDO_INTROSPECCAO
        enviado = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not segredo or not hmac.compare_digest(enviado.encode(), segredo.encode()):
            return Response({"error": "invalid_client"}, status=status.HTTP_401_UNAUTHORIZED)
        return Response(oauth.introspectar(request.data.get("token")))


class PedidoOAuthAPIView(_SomenteJwt):
    """Tela /autorizar: confere o pedido (GET) e grava a decisão da pessoa (POST)."""

    throttle_scope = "oauth_consentimento"

    @staticmethod
    def _erro(exc):
        if isinstance(exc, oauth.ErroDeRetorno):
            return Response(
                {"detail": exc.descricao, "redirecionar": exc.url}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        parameters=[ParametrosPedidoOAuthSerializer],
        responses={200: PedidoOAuthSerializer, 400: ErroPedidoOAuthSerializer},
    )
    def get(self, request):
        try:
            pedido = oauth.validar_pedido(request.query_params)
        except (oauth.ErroSemRetorno, oauth.ErroDeRetorno) as exc:
            return self._erro(exc)
        escritorios = [m.escritorio for m in memberships_do_usuario(request.user)]
        return Response(
            PedidoOAuthSerializer(
                {
                    "aplicativo": pedido["cliente"].nome,
                    "destino": urlsplit(pedido["redirect_uri"]).hostname,
                    "escopo": oauth.ESCOPO,
                    "escritorios": escritorios,
                }
            ).data
        )

    @extend_schema(
        request=ConsentimentoOAuthSerializer,
        responses={200: RedirecionamentoOAuthSerializer, 400: ErroPedidoOAuthSerializer},
    )
    def post(self, request):
        serializer = ConsentimentoOAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dados = serializer.validated_data
        try:
            pedido = oauth.validar_pedido(dados)
        except (oauth.ErroSemRetorno, oauth.ErroDeRetorno) as exc:
            return self._erro(exc)
        if not dados["permitir"]:
            return Response({"redirecionar": oauth.negar(pedido)})
        try:
            url = oauth.autorizar(
                usuario=request.user, pedido=pedido, escritorio_id=dados.get("escritorio_id")
            )
        except oauth.ErroOAuth as exc:
            return Response({"detail": exc.descricao}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"redirecionar": url})


class ConexoesOAuthAPIView(_SomenteJwt):
    @extend_schema(responses=ConexaoOAuthSerializer(many=True))
    def get(self, request):
        return Response(ConexaoOAuthSerializer(oauth.conexoes_do_usuario(request.user), many=True).data)


class ConexaoOAuthDetalheAPIView(_SomenteJwt):
    @extend_schema(responses={204: None})
    def delete(self, request, conexao_id):
        oauth.revogar_conexao(usuario=request.user, conexao_id=conexao_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
