"""Ciclo de vida da conta: cadastro, convite, recuperação de senha.

Mesmo molde de ``organizations.services``: funções com argumentos nomeados,
transacionais, que gravam auditoria. As views só traduzem HTTP.
"""

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import ValidationError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from auditlog.models import EventoAuditoria
from auditlog.services import registrar_evento_auditoria
from organizations.models import Escritorio, MembroEscritorio
from organizations.selectors import convite_pendente_por_token

from .emails import enviar_reset_senha, enviar_verificacao_email
from .models import AceiteTermos, EmailVerificado
from .tokens_api import revogar_tokens_api

logger = logging.getLogger(__name__)


def _normalizar_email(email):
    return email.strip().lower()


def _validar_senha(senha, usuario):
    """Aplica os validadores do Django e devolve erro no formato da API."""
    try:
        validate_password(senha, usuario)
    except DjangoValidationError as exc:
        raise ValidationError({"senha": list(exc.messages)}) from exc


def _email_em_uso(email):
    User = get_user_model()
    return (
        User.objects.filter(email__iexact=email).exists()
        or User.objects.filter(username__iexact=email).exists()
    )


def _criar_usuario(*, nome, email, senha, ip):
    """Cria o usuário e registra o aceite dos termos vigentes.

    O e-mail é o nome de usuário: o login já aceita e-mail, e assim não existe
    um segundo identificador para a pessoa lembrar.
    """
    User = get_user_model()
    candidato = User(username=email, email=email, first_name=nome)
    _validar_senha(senha, candidato)
    usuario = User.objects.create_user(
        username=email, email=email, password=senha, first_name=nome
    )
    AceiteTermos.objects.create(usuario=usuario, versao=settings.TERMOS_VERSAO, ip=ip)
    return usuario


@transaction.atomic
def registrar_conta(*, nome, email, senha, escritorio_nome, ip=None):
    """Cria usuário, escritório e vínculo de proprietário numa única transação."""
    email = _normalizar_email(email)
    if _email_em_uso(email):
        raise ValidationError({"email": ["Este e-mail já está em uso."]})

    usuario = _criar_usuario(nome=nome, email=email, senha=senha, ip=ip)
    escritorio = Escritorio.objects.create(nome=escritorio_nome, criado_por=usuario)
    MembroEscritorio.objects.create(
        escritorio=escritorio, usuario=usuario, papel=MembroEscritorio.Papel.OWNER
    )
    registrar_evento_auditoria(
        escritorio=escritorio,
        ator=usuario,
        acao="escritorio.criado",
        recurso_tipo="escritorio",
        recurso_id=escritorio.pk,
        alteracoes={"nome": escritorio_nome},
    )
    transaction.on_commit(lambda: _enviar_verificacao_sem_falhar(usuario))
    return usuario


@transaction.atomic
def aceitar_convite(*, token, senha, nome="", aceite_termos=False, ip=None):
    """Aceita um convite, criando a conta se o e-mail ainda não tiver uma.

    Quem já tem conta prova que é o dono dela com a senha atual: o token prova
    controle da caixa de e-mail, mas não deve bastar para entrar numa conta
    que já existe.
    """
    convite = convite_pendente_por_token(token, bloquear=True)
    if convite is None:
        raise ValidationError({"detail": "Convite inválido ou expirado."})

    User = get_user_model()
    # O username também conta: quem trocou de e-mail segue dono do endereço com que se cadastrou.
    usuario = User.objects.filter(
        Q(email__iexact=convite.email) | Q(username__iexact=convite.email)
    ).first()
    if usuario:
        if not usuario.is_active or not usuario.check_password(senha):
            raise ValidationError({"senha": ["Senha incorreta para a conta existente."]})
        if MembroEscritorio.objects.filter(
            escritorio=convite.escritorio, usuario=usuario
        ).exists():
            raise ValidationError({"detail": "Esta conta já faz parte do escritório."})
    else:
        if not aceite_termos:
            raise ValidationError(
                {"aceite_termos": ["É necessário aceitar os termos para criar a conta."]}
            )
        usuario = _criar_usuario(
            nome=nome or convite.email.split("@")[0],
            email=convite.email,
            senha=senha,
            ip=ip,
        )

    # O token do convite chegou pela caixa de e-mail: isso já prova o controle dela.
    if usuario.email.lower() == convite.email.lower():
        EmailVerificado.objects.get_or_create(usuario=usuario)
    MembroEscritorio.objects.create(
        escritorio=convite.escritorio, usuario=usuario, papel=convite.papel
    )
    convite.aceito_em = timezone.now()
    convite.save(update_fields=("aceito_em",))
    registrar_evento_auditoria(
        escritorio=convite.escritorio,
        ator=usuario,
        acao="convite.aceito",
        recurso_tipo="convite_escritorio",
        recurso_id=convite.pk,
        alteracoes={"papel": convite.papel},
    )
    return usuario


_SALT_VERIFICACAO = "accounts.verificacao-email"


def email_esta_verificado(usuario):
    return EmailVerificado.objects.filter(usuario=usuario).exists()


def enviar_verificacao(usuario, enviar=enviar_verificacao_email):
    """Envia o link de confirmação, a menos que o e-mail já esteja confirmado.

    O token leva o e-mail junto: se a conta mudar de e-mail, links antigos
    deixam de valer.
    """
    if email_esta_verificado(usuario):
        return
    token = signing.dumps({"uid": usuario.pk, "email": usuario.email}, salt=_SALT_VERIFICACAO)
    enviar(usuario=usuario, token=token)


def _enviar_verificacao_sem_falhar(usuario):
    """Roda depois do commit: a conta já existe, falha de SMTP não pode derrubar o cadastro.

    A pessoa pede novo link em "reenviar"; aqui só fica o registro no log.
    """
    try:
        enviar_verificacao(usuario)
    except Exception:
        logger.exception("Falha ao enviar a verificação de e-mail do usuário %s", usuario.pk)


def registrar_troca_de_email(usuario):
    """O e-mail novo ainda não foi provado: volta a pedir confirmação, agora para ele."""
    EmailVerificado.objects.filter(usuario=usuario).delete()
    transaction.on_commit(lambda: _enviar_verificacao_sem_falhar(usuario))


def confirmar_email(*, token):
    """Marca o e-mail como verificado. Repetir o link é inofensivo."""
    invalido = ValidationError({"detail": "Link inválido ou expirado."})
    try:
        dados = signing.loads(
            token,
            salt=_SALT_VERIFICACAO,
            max_age=settings.VERIFICACAO_EMAIL_HORAS * 3600,
        )
        usuario = get_user_model().objects.get(pk=dados["uid"], is_active=True)
    except (signing.BadSignature, KeyError, TypeError, get_user_model().DoesNotExist):
        raise invalido
    if usuario.email != dados["email"]:
        raise invalido
    EmailVerificado.objects.get_or_create(usuario=usuario)
    return usuario


def solicitar_reset_senha(*, email, enviar=enviar_reset_senha):
    """Envia o link se a conta existir. Não revela se existe: a resposta é igual."""
    usuario = (
        get_user_model()
        .objects.filter(email__iexact=_normalizar_email(email), is_active=True)
        .first()
    )
    if usuario and usuario.has_usable_password():
        try:
            enviar(
                usuario=usuario,
                uid=urlsafe_base64_encode(force_bytes(usuario.pk)),
                token=default_token_generator.make_token(usuario),
            )
        except Exception:  # um erro só para conta existente revelaria quem tem conta
            logger.exception("Falha ao enviar a recuperação de senha do usuário %s", usuario.pk)


@transaction.atomic
def confirmar_reset_senha(*, uid, token, nova_senha):
    """Troca a senha. O token do Django é de uso único: muda quando a senha muda."""
    invalido = ValidationError({"detail": "Link inválido ou expirado."})
    try:
        usuario = get_user_model().objects.get(
            pk=urlsafe_base64_decode(uid).decode(), is_active=True
        )
    except (TypeError, ValueError, OverflowError, get_user_model().DoesNotExist):
        raise invalido
    if not default_token_generator.check_token(usuario, token):
        raise invalido

    _validar_senha(nova_senha, usuario)
    usuario.set_password(nova_senha)
    usuario.save(update_fields=("password",))
    # Quem recupera a senha costuma fazê-lo porque suspeita de acesso indevido:
    # as sessões abertas com a senha antiga não podem sobreviver.
    revogar_sessoes(usuario)
    return usuario


def revogar_sessoes(usuario):
    """Invalida todos os refresh tokens e os tokens de API da pessoa.

    O access token em circulação segue valendo até expirar (minutos): ele não é
    consultado no servidor. Conta desativada é barrada na hora, de qualquer forma.
    """
    for token in OutstandingToken.objects.filter(user=usuario):
        BlacklistedToken.objects.get_or_create(token=token)
    revogar_tokens_api(usuario)


def exportar_dados(*, usuario):
    """Tudo o que o sistema guarda sobre a PESSOA (art. 18, II, da LGPD).

    Dados de clientes e processos pertencem ao escritório, que é quem responde
    por eles perante os titulares; não saem por aqui. Hash de senha nunca sai.
    """
    memberships = MembroEscritorio.objects.filter(usuario=usuario).select_related(
        "escritorio"
    )
    atividade = EventoAuditoria.objects.filter(ator=usuario).select_related("escritorio")
    limite = 10_000
    eventos = list(atividade[:limite])
    return {
        "exportado_em": timezone.now().isoformat(),
        "conta": {
            "id": usuario.pk,
            "email": usuario.email,
            "nome": usuario.first_name,
            "cadastrada_em": usuario.date_joined.isoformat(),
            "ultimo_acesso": usuario.last_login.isoformat() if usuario.last_login else None,
        },
        "aceites_termos": [
            {"versao": a.versao, "aceito_em": a.aceito_em.isoformat(), "ip": a.ip}
            for a in AceiteTermos.objects.filter(usuario=usuario)
        ],
        "escritorios": [
            {
                "id": str(m.escritorio_id),
                "nome": m.escritorio.nome,
                "papel": m.papel,
                "status": m.status,
                "desde": m.criado_em.isoformat(),
            }
            for m in memberships
        ],
        "atividade": [
            {
                "escritorio": e.escritorio.nome,
                "acao": e.acao,
                "recurso": f"{e.recurso_tipo}:{e.recurso_id}",
                "em": e.criado_em.isoformat(),
            }
            for e in eventos
        ],
        "atividade_truncada": atividade.count() > limite,
    }


def _escritorios_que_ficariam_sem_proprietario(usuario):
    """Escritórios com equipe em que a pessoa é o único proprietário ativo."""
    bloqueados = []
    donos = MembroEscritorio.objects.filter(
        usuario=usuario,
        papel=MembroEscritorio.Papel.OWNER,
        status=MembroEscritorio.Status.ATIVO,
    ).select_related("escritorio")
    for membro in donos:
        ativos = MembroEscritorio.objects.filter(
            escritorio=membro.escritorio, status=MembroEscritorio.Status.ATIVO
        ).exclude(usuario=usuario)
        outro_dono = ativos.filter(papel=MembroEscritorio.Papel.OWNER).exists()
        if ativos.exists() and not outro_dono:
            bloqueados.append(membro.escritorio.nome)
    return bloqueados


@transaction.atomic
def excluir_conta(*, usuario, senha):
    """Anonimiza a conta (art. 18, VI, da LGPD).

    Anonimiza em vez de apagar a linha: processos, eventos e auditoria do
    escritório apontam para ela, e a trilha de auditoria é imutável. O que
    identifica a pessoa (nome, e-mail, senha) desaparece.

    Escritório em que ela era a única pessoa é desativado, não apagado: os dados
    de clientes têm prazo de guarda por obrigação profissional.
    """
    if not usuario.check_password(senha):
        raise ValidationError({"senha": ["Senha incorreta."]})

    bloqueados = _escritorios_que_ficariam_sem_proprietario(usuario)
    if bloqueados:
        raise ValidationError(
            {
                "detail": "Transfira a propriedade antes de excluir a conta, em: "
                + ", ".join(bloqueados)
                + "."
            }
        )

    ativos = MembroEscritorio.objects.filter(
        usuario=usuario, status=MembroEscritorio.Status.ATIVO
    ).select_related("escritorio")
    for membro in ativos:
        sozinha = not MembroEscritorio.objects.filter(
            escritorio=membro.escritorio, status=MembroEscritorio.Status.ATIVO
        ).exclude(usuario=usuario).exists()
        if sozinha:
            membro.escritorio.ativo = False
            membro.escritorio.save(update_fields=("ativo", "atualizado_em"))
        registrar_evento_auditoria(
            escritorio=membro.escritorio,
            ator=usuario,
            acao="conta.excluida",
            recurso_tipo="usuario",
            recurso_id=usuario.pk,
            alteracoes={"escritorio_desativado": sozinha},
        )

    MembroEscritorio.objects.filter(usuario=usuario).update(
        status=MembroEscritorio.Status.SUSPENSO
    )
    usuario.username = f"excluido-{usuario.pk}"
    usuario.email = ""
    usuario.first_name = "Conta excluída"
    usuario.last_name = ""
    usuario.is_active = False
    usuario.set_unusable_password()
    usuario.save()
    revogar_sessoes(usuario)
