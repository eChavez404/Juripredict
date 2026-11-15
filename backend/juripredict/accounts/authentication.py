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

from organizations.selectors import memberships_do_usuario
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

        token = (
            TokenApi.objects.select_related("usuario", "conexao__cliente")
            .filter(hash=hash_token(bruto))
            .first()
        )
        if token is None or not token.ativo or not token.usuario.is_active:
            raise AuthenticationFailed("Token inválido, expirado ou revogado.")
        membro = self._membro_da_conexao(token) if token.conexao_id else None
        if token.conexao_id and membro is None:
            raise AuthenticationFailed("Token inválido, expirado ou revogado.")
        # Token de OAuth não lê auth/me/: ele listaria os outros escritórios da pessoa.
        permitida = ROTAS_PERMITIDAS.match(request.path) and not (
            token.conexao_id and request.path.endswith("/auth/me/")
        )
        if request.method not in SAFE_METHODS or not permitida:
            # o middleware de auditoria lê isto: a tentativa negada também precisa de registro
            request._request.token_api_negado = token
            raise PermissionDenied("Este token só permite consultas em rotas de leitura.")
        if membro is not None:
            # O escritório vem da conexão, não do cabeçalho X-Escritorio-ID: o token só
            # enxerga o que a pessoa autorizou na tela de consentimento.
            request._request.membro_escritorio = membro
            request._request.escritorio = membro.escritorio

        agora = timezone.now()
        if token.ultimo_uso_em is None or agora - token.ultimo_uso_em > INTERVALO_REGISTRO_USO:
            TokenApi.objects.filter(pk=token.pk).update(ultimo_uso_em=agora)
        return token.usuario, token

    @staticmethod
    def _membro_da_conexao(token):
        """Vínculo ativo com o escritório autorizado, ou ``None`` se a conexão foi
        revogada ou a pessoa saiu do escritório."""
        if not token.conexao.ativa:
            return None
        return memberships_do_usuario(token.usuario).filter(
            escritorio_id=token.conexao.escritorio_id
        ).first()
