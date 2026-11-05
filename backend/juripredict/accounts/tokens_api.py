"""Ciclo de vida dos tokens de API: criar, listar, revogar.

Criar exige a senha de novo: um token vale mais que uma sessão (dura meses e não
expira com o logout), então uma sessão esquecida aberta não pode emitir um.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from auditlog.services import registrar_evento_auditoria
from organizations.models import MembroEscritorio
from organizations.tokens import gerar_token, hash_token

from .authentication import PREFIXO_TOKEN
from .models import TokenApi


def _auditar(usuario, acao, token):
    """Registra no log de cada escritório em que a pessoa atua.

    O token é da pessoa, não de um escritório; quem administra um escritório precisa
    saber que um membro dele emitiu ou revogou uma credencial de agente.
    """
    escritorios = MembroEscritorio.objects.filter(
        usuario=usuario, status=MembroEscritorio.Status.ATIVO
    ).select_related("escritorio")
    for membro in escritorios:
        registrar_evento_auditoria(
            escritorio=membro.escritorio,
            ator=usuario,
            acao=acao,
            recurso_tipo="token_api",
            recurso_id=token.pk,
            alteracoes={"nome": token.nome, "credencial": token.prefixo},
        )


def tokens_do_usuario(usuario):
    return TokenApi.objects.filter(usuario=usuario)


@transaction.atomic
def criar_token_api(*, usuario, nome, senha, validade_dias=None):
    """Devolve ``(token_api, texto_do_token)``. O texto só existe nesta resposta."""
    if not usuario.check_password(senha):
        raise ValidationError({"senha": ["Senha incorreta."]})
    ativos = [t for t in tokens_do_usuario(usuario) if t.ativo]
    if len(ativos) >= settings.API_TOKEN_MAX_ATIVOS:
        raise ValidationError(
            {"detail": f"Limite de {settings.API_TOKEN_MAX_ATIVOS} tokens ativos. Revogue um antes."}
        )

    texto = PREFIXO_TOKEN + gerar_token()
    dias = validade_dias or settings.API_TOKEN_VALIDADE_DIAS
    token = TokenApi.objects.create(
        usuario=usuario,
        nome=nome.strip(),
        prefixo=texto[:10],
        hash=hash_token(texto),
        expira_em=timezone.now() + timedelta(days=dias),
    )
    _auditar(usuario, "token_api.criado", token)
    return token, texto


@transaction.atomic
def revogar_token_api(*, usuario, token_id):
    token = tokens_do_usuario(usuario).filter(pk=token_id).first()
    if token is None:
        raise ValidationError({"detail": "Token não encontrado."})
    if token.revogado_em is None:
        token.revogado_em = timezone.now()
        token.save(update_fields=("revogado_em",))
        _auditar(usuario, "token_api.revogado", token)
    return token


def revogar_tokens_api(usuario):
    """Revoga todos (troca de senha, exclusão da conta). Sem auditoria por token:
    o evento da própria troca de senha já conta o que houve."""
    return tokens_do_usuario(usuario).filter(revogado_em__isnull=True).update(
        revogado_em=timezone.now()
    )
