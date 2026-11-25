"""Servidor de autorização OAuth 2.1 do conector MCP remoto.

O advogado conecta um aplicativo (o Claude, o agente do JuriPredict) colando uma URL.
O aplicativo descobre este servidor pelos metadados (RFC 8414), registra-se (DCR,
RFC 7591), manda a pessoa à tela /autorizar, recebe um código e o troca por tokens,
com PKCE S256 obrigatório.

O access token é um ``TokenApi``: herda a lista fixa de rotas de leitura, a revogação
e a auditoria de ``accounts.authentication``. Ele só enxerga o escritório escolhido no
consentimento. O refresh token gira a cada uso, e o reuso de um já trocado revoga a
conexão inteira.

Erro de cliente ou de redirect_uri nunca redireciona: devolver um código a um endereço
não registrado seria entregá-lo a quem forjou o pedido.
"""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import NotFound

from auditlog.services import registrar_evento_auditoria
from organizations.selectors import memberships_do_usuario
from organizations.tokens import gerar_token, hash_token

from .authentication import PREFIXO_TOKEN
from .models import ClienteOAuth, CodigoAutorizacao, ConexaoOAuth, RenovacaoOAuth, TokenApi

ESCOPO = "leitura"
MAX_REDIRECTS = 10
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1"}
# Dois pedidos de renovação simultâneos com o mesmo token são comuns em clientes reais;
# só o reuso fora desta janela é tratado como roubo.
TOLERANCIA_REUSO = timedelta(seconds=30)


class ErroOAuth(Exception):
    """Erro no formato do RFC 6749: ``error`` + ``error_description``."""

    def __init__(self, erro, descricao, status=400):
        super().__init__(descricao)
        self.erro, self.descricao, self.status = erro, descricao, status

    def corpo(self):
        return {"error": self.erro, "error_description": self.descricao}


class ErroSemRetorno(Exception):
    """Pedido que não pode voltar ao aplicativo: cliente desconhecido ou redirect_uri não
    registrado. A tela mostra o motivo e para."""


class ErroDeRetorno(Exception):
    """Pedido inválido com destino conhecido: o erro volta ao aplicativo pela URL."""

    def __init__(self, pedido, erro, descricao):
        super().__init__(descricao)
        self.descricao = descricao
        self.url = url_de_retorno(
            pedido["redirect_uri"], error=erro, error_description=descricao,
            state=pedido["state"], iss=settings.OAUTH_EMISSOR,
        )


def metadados():
    emissor = settings.OAUTH_EMISSOR
    metodos = list(ClienteOAuth.Autenticacao.values)
    return {
        "issuer": emissor,
        "authorization_endpoint": f"{emissor}/autorizar",
        "token_endpoint": f"{emissor}/oauth/token",
        "registration_endpoint": f"{emissor}/oauth/registrar",
        "revocation_endpoint": f"{emissor}/oauth/revogar",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": metodos,
        "revocation_endpoint_auth_methods_supported": metodos,
        "scopes_supported": [ESCOPO],
        "authorization_response_iss_parameter_supported": True,
    }


def url_de_retorno(redirect_uri, **params):
    partes = urlsplit(redirect_uri)
    query = parse_qsl(partes.query, keep_blank_values=True)
    query += [(chave, valor) for chave, valor in params.items() if valor]
    return urlunsplit(partes._replace(query=urlencode(query)))


# ------------------------------------------------------------------ registro (DCR)
def _redirect_valido(uri):
    """https, ou http só no próprio computador (aplicativos de desktop, RFC 8252)."""
    if not isinstance(uri, str) or len(uri) > 2000:
        return False
    partes = urlsplit(uri)
    if partes.fragment or not partes.hostname:
        return False
    return partes.scheme == "https" or (partes.scheme == "http" and partes.hostname in HOSTS_LOCAIS)


def registrar_cliente(dados):
    """Devolve ``(cliente, segredo)``; o segredo é ``None`` para cliente público."""
    if not settings.OAUTH_RECURSOS:
        raise ErroOAuth("temporarily_unavailable", "O conector MCP não está ativo.", status=503)
    uris = dados.get("redirect_uris")
    if (
        not isinstance(uris, list) or not 0 < len(uris) <= MAX_REDIRECTS
        or not all(_redirect_valido(uri) for uri in uris)
    ):
        raise ErroOAuth(
            "invalid_redirect_uri",
            f"Informe de 1 a {MAX_REDIRECTS} redirect_uris com https (ou http em localhost).",
        )
    metodo = dados.get("token_endpoint_auth_method") or ClienteOAuth.Autenticacao.NENHUMA
    if metodo not in ClienteOAuth.Autenticacao.values:
        raise ErroOAuth("invalid_client_metadata", "token_endpoint_auth_method não suportado.")
    segredo = None if metodo == ClienteOAuth.Autenticacao.NENHUMA else gerar_token()
    cliente = ClienteOAuth.objects.create(
        client_id=secrets.token_urlsafe(24),
        nome=" ".join(str(dados.get("client_name") or "Aplicativo sem nome").split())[:120],
        redirect_uris=uris,
        autenticacao=metodo,
        segredo_hash=hash_token(segredo) if segredo else "",
    )
    return cliente, segredo


def resposta_registro(cliente, segredo):
    corpo = {
        "client_id": cliente.client_id,
        "client_id_issued_at": int(cliente.criado_em.timestamp()),
        "client_name": cliente.nome,
        "redirect_uris": cliente.redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": cliente.autenticacao,
        "scope": ESCOPO,
    }
    if segredo:
        corpo.update(client_secret=segredo, client_secret_expires_at=0)
    return corpo


def autenticar_cliente(client_id, client_secret):
    cliente = ClienteOAuth.objects.filter(client_id=client_id or "").first()
    if cliente is None:
        raise ErroOAuth("invalid_client", "Aplicativo desconhecido.", status=401)
    if cliente.autenticacao != ClienteOAuth.Autenticacao.NENHUMA and not hmac.compare_digest(
        hash_token(client_secret or ""), cliente.segredo_hash
    ):
        raise ErroOAuth("invalid_client", "Credenciais do aplicativo inválidas.", status=401)
    return cliente


# ------------------------------------------------------------------ consentimento
def _recurso(pedido_recurso):
    """O recurso pedido (RFC 8707), ou o padrão. Compara sem a barra final."""
    if not pedido_recurso:
        return settings.OAUTH_RECURSOS[0] if settings.OAUTH_RECURSOS else None
    for recurso in settings.OAUTH_RECURSOS:
        if recurso.rstrip("/") == pedido_recurso.rstrip("/"):
            return recurso
    return None


def validar_pedido(params):
    """Confere o pedido de autorização e devolve o que a tela e o consentimento usam."""
    cliente = ClienteOAuth.objects.filter(client_id=params.get("client_id") or "").first()
    if cliente is None:
        raise ErroSemRetorno("Aplicativo desconhecido. Refaça a conexão a partir dele.")
    redirect_uri = params.get("redirect_uri") or ""
    if not redirect_uri and len(cliente.redirect_uris) == 1:
        redirect_uri = cliente.redirect_uris[0]
    if redirect_uri not in cliente.redirect_uris:
        raise ErroSemRetorno("O endereço de retorno não foi registrado por este aplicativo.")

    pedido = {"cliente": cliente, "redirect_uri": redirect_uri, "state": params.get("state") or ""}
    if params.get("response_type") != "code":
        raise ErroDeRetorno(pedido, "unsupported_response_type", "Só response_type=code é aceito.")
    desafio = params.get("code_challenge") or ""
    if params.get("code_challenge_method") != "S256" or not 43 <= len(desafio) <= 128:
        raise ErroDeRetorno(pedido, "invalid_request", "PKCE com code_challenge_method=S256 é obrigatório.")
    recurso = _recurso(params.get("resource") or "")
    if recurso is None:
        raise ErroDeRetorno(pedido, "invalid_target", "Recurso desconhecido.")
    pedido.update(code_challenge=desafio, recurso=recurso)
    return pedido


def _membro(usuario, escritorio_id):
    try:
        escritorio_uuid = uuid.UUID(str(escritorio_id))
    except (TypeError, ValueError):
        return None
    return memberships_do_usuario(usuario).filter(escritorio_id=escritorio_uuid).first()


def autorizar(*, usuario, pedido, escritorio_id):
    """Grava o consentimento e devolve a URL de volta ao aplicativo, com o código."""
    membro = _membro(usuario, escritorio_id)
    if membro is None:
        raise ErroOAuth("invalid_request", "Escritório indisponível para esta conta.")
    codigo = gerar_token()
    with transaction.atomic():
        conexao = ConexaoOAuth.objects.filter(
            usuario=usuario, cliente=pedido["cliente"], escritorio=membro.escritorio,
            recurso=pedido["recurso"], revogada_em__isnull=True,
        ).first()
        if conexao is None:
            conexao = ConexaoOAuth.objects.create(
                usuario=usuario, cliente=pedido["cliente"], escritorio=membro.escritorio,
                recurso=pedido["recurso"],
            )
            _auditar(conexao, "oauth.conexao_criada", ator=usuario)
        CodigoAutorizacao.objects.create(
            conexao=conexao,
            hash=hash_token(codigo),
            redirect_uri=pedido["redirect_uri"],
            code_challenge=pedido["code_challenge"],
            expira_em=timezone.now() + timedelta(seconds=settings.OAUTH_CODIGO_SEGUNDOS),
        )
    return url_de_retorno(
        pedido["redirect_uri"], code=codigo, state=pedido["state"], iss=settings.OAUTH_EMISSOR
    )


def negar(pedido):
    return url_de_retorno(
        pedido["redirect_uri"], error="access_denied", error_description="A pessoa negou o acesso.",
        state=pedido["state"], iss=settings.OAUTH_EMISSOR,
    )


# ------------------------------------------------------------------ tokens
def _pkce_confere(verificador, desafio):
    if not isinstance(verificador, str) or not 43 <= len(verificador) <= 128:
        return False
    calculado = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
    return hmac.compare_digest(calculado.rstrip(b"=").decode(), desafio)


def _utilizavel(conexao):
    """Conexão ativa, pessoa ativa e ainda membro do escritório autorizado."""
    return (
        conexao.ativa
        and conexao.usuario.is_active
        and memberships_do_usuario(conexao.usuario).filter(escritorio=conexao.escritorio_id).exists()
    )


def _emitir(conexao):
    agora = timezone.now()
    acesso = PREFIXO_TOKEN + gerar_token()
    TokenApi.objects.create(
        usuario=conexao.usuario,
        nome=conexao.cliente.nome[:80],
        prefixo=acesso[:10],
        hash=hash_token(acesso),
        expira_em=agora + timedelta(seconds=settings.OAUTH_ACESSO_SEGUNDOS),
        conexao=conexao,
    )
    # sem o prefixo jp_: um refresh token não serve como Bearer na API
    renovacao = gerar_token()
    RenovacaoOAuth.objects.create(
        conexao=conexao,
        hash=hash_token(renovacao),
        expira_em=agora + timedelta(days=settings.OAUTH_RENOVACAO_DIAS),
    )
    return {
        "access_token": acesso,
        "token_type": "Bearer",
        "expires_in": settings.OAUTH_ACESSO_SEGUNDOS,
        "refresh_token": renovacao,
        "scope": ESCOPO,
    }


def trocar_codigo(*, cliente, codigo, redirect_uri, code_verifier):
    # O erro sai depois do commit: marcar o código como usado e revogar por reuso
    # precisam valer mesmo quando a troca falha.
    with transaction.atomic():
        registro = (
            CodigoAutorizacao.objects.select_for_update()
            .select_related("conexao__cliente", "conexao__usuario")
            .filter(hash=hash_token(codigo or ""))
            .first()
        )
        erro = _conferir_codigo(registro, cliente, redirect_uri, code_verifier)
        tokens = None if erro else _emitir(registro.conexao)
    if erro:
        raise erro
    return tokens


def _conferir_codigo(registro, cliente, redirect_uri, code_verifier):
    agora = timezone.now()
    if registro is None or registro.conexao.cliente_id != cliente.pk:
        return ErroOAuth("invalid_grant", "Código inválido.")
    if registro.usado_em is not None:
        # quem apresenta um código já trocado pode ser um terceiro (RFC 6749, 4.1.2)
        _revogar(registro.conexao, "oauth.reuso_de_codigo")
        return ErroOAuth("invalid_grant", "Código já utilizado.")
    registro.usado_em = agora
    registro.save(update_fields=["usado_em"])
    if registro.expira_em <= agora:
        return ErroOAuth("invalid_grant", "Código expirado.")
    if redirect_uri and redirect_uri != registro.redirect_uri:
        return ErroOAuth("invalid_grant", "redirect_uri diferente do pedido.")
    if not _pkce_confere(code_verifier, registro.code_challenge):
        return ErroOAuth("invalid_grant", "code_verifier não confere.")
    if not _utilizavel(registro.conexao):
        return ErroOAuth("invalid_grant", "Acesso revogado.")
    return None


def renovar(*, cliente, renovacao):
    with transaction.atomic():
        registro = (
            RenovacaoOAuth.objects.select_for_update()
            .select_related("conexao__cliente", "conexao__usuario")
            .filter(hash=hash_token(renovacao or ""))
            .first()
        )
        erro = _conferir_renovacao(registro, cliente)
        tokens = None if erro else _emitir(registro.conexao)
    if erro:
        raise erro
    return tokens


def _conferir_renovacao(registro, cliente):
    agora = timezone.now()
    if registro is None or registro.conexao.cliente_id != cliente.pk:
        return ErroOAuth("invalid_grant", "Token de renovação inválido.")
    if registro.usado_em is not None:
        if agora - registro.usado_em > TOLERANCIA_REUSO:
            _revogar(registro.conexao, "oauth.reuso_de_renovacao")
        return ErroOAuth("invalid_grant", "Token de renovação já utilizado.")
    registro.usado_em = agora
    registro.save(update_fields=["usado_em"])
    if registro.expira_em <= agora or not _utilizavel(registro.conexao):
        return ErroOAuth("invalid_grant", "Token de renovação expirado ou revogado.")
    return None


def revogar_token(*, cliente, texto):
    """RFC 7009. Revogar o access ou o refresh token desliga a conexão inteira: é o que o
    aplicativo faz ao se desconectar. Token desconhecido não é erro."""
    hash_ = hash_token(texto or "")
    conexao = (
        ConexaoOAuth.objects.filter(cliente=cliente, renovacoes__hash=hash_).first()
        or ConexaoOAuth.objects.filter(cliente=cliente, tokens__hash=hash_).first()
    )
    if conexao is not None:
        with transaction.atomic():
            _revogar(conexao, "oauth.conexao_revogada")


def introspectar(texto):
    """RFC 7662, para o serviço MCP. Só tokens emitidos por OAuth são respondidos."""
    token = (
        TokenApi.objects.select_related("usuario", "conexao__cliente", "conexao__usuario")
        .filter(hash=hash_token(texto or ""), conexao__isnull=False)
        .first()
    )
    if token is None or not token.ativo or not _utilizavel(token.conexao):
        return {"active": False}
    conexao = token.conexao
    return {
        "active": True,
        "client_id": conexao.cliente.client_id,
        "scope": ESCOPO,
        "token_type": "Bearer",
        "exp": int(token.expira_em.timestamp()),
        "iat": int(token.criado_em.timestamp()),
        "sub": str(token.usuario_id),
        "aud": conexao.recurso,
        "iss": settings.OAUTH_EMISSOR,
        "escritorio_id": str(conexao.escritorio_id),
    }


# ------------------------------------------------------------------ aplicativos conectados
def conexoes_do_usuario(usuario):
    return (
        ConexaoOAuth.objects.filter(usuario=usuario, revogada_em__isnull=True)
        .select_related("cliente", "escritorio")
        .annotate(ultimo_uso_em=Max("tokens__ultimo_uso_em"))
    )


def revogar_conexao(*, usuario, conexao_id):
    conexao = ConexaoOAuth.objects.filter(usuario=usuario, pk=conexao_id).select_related(
        "cliente", "escritorio"
    ).first()
    if conexao is None:
        raise NotFound("Conexão não encontrada.")
    with transaction.atomic():
        _revogar(conexao, "oauth.conexao_revogada", ator=usuario)


def _revogar(conexao, acao, ator=None):
    if conexao.revogada_em is not None:
        return
    agora = timezone.now()
    conexao.revogada_em = agora
    conexao.save(update_fields=["revogada_em"])
    conexao.tokens.filter(revogado_em__isnull=True).update(revogado_em=agora)
    _auditar(conexao, acao, ator=ator or conexao.usuario)


def _auditar(conexao, acao, ator):
    registrar_evento_auditoria(
        escritorio=conexao.escritorio,
        ator=ator,
        acao=acao,
        recurso_tipo="conexao_oauth",
        recurso_id=conexao.pk,
        alteracoes={"aplicativo": conexao.cliente.nome},
    )
