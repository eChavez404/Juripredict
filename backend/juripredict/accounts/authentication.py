"""Autenticação por token de API: o único ponto que decide o que um agente pode fazer.

O controle fica aqui, e não em permissões espalhadas pelas views, porque as views
trocam ``permission_classes`` livremente. Aqui a regra vale para qualquer rota nova:
se não estiver na lista, o token não entra.
"""

import re
from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import SAFE_METHODS

from organizations.tokens import hash_token

from .models import TokenApi

PREFIXO_TOKEN = "jp_"

# Rotas de leitura que o MCP usa. Ficam de fora, de propósito: clientes (CPF/CNPJ),
# auditoria, exportação de dados, exclusão de conta, troca de senha, equipe e o próprio
# gerenciamento de tokens.
ROTAS_PERMITIDAS = re.compile(
    r"^/api/v1/(?:"
    r"(?:processos|eventos)/(?:\d+/(?:andamentos/|documentos/)?)?"
    r"|jurimetria/(?:processos/)?|dashboard/|pendencias/|prazos/calcular/|auth/me/"
    r")$"
)

# Gravar o último uso a cada requisição seria uma escrita por consulta.
INTERVALO_REGISTRO_USO = timedelta(minutes=1)


def e_token_api(auth):
    return isinstance(auth, TokenApi)


class TokenApiAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return 'Bearer realm="api"'

    def authenticate(self, request):
        partes = get_authorization_header(request).split()
        if len(partes) != 2 or partes[0].lower() != b"bearer":
            return None
        bruto = partes[1].decode(errors="ignore")
        if not bruto.startswith(PREFIXO_TOKEN):
            return None  # é um JWT: segue para a autenticação normal

        token = TokenApi.objects.select_related("usuario").filter(hash=hash_token(bruto)).first()
        if token is None or not token.ativo or not token.usuario.is_active:
            raise AuthenticationFailed("Token inválido, expirado ou revogado.")
        if request.method not in SAFE_METHODS or not ROTAS_PERMITIDAS.match(request.path):
            # o middleware de auditoria lê isto: a tentativa negada também precisa de registro
            request._request.token_api_negado = token
            raise PermissionDenied("Este token só permite consultas em rotas de leitura.")

        agora = timezone.now()
        if token.ultimo_uso_em is None or agora - token.ultimo_uso_em > INTERVALO_REGISTRO_USO:
            TokenApi.objects.filter(pk=token.pk).update(ultimo_uso_em=agora)
        return token.usuario, token
