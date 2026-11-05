from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from auditlog.services import registrar_evento_auditoria

from .emails import enviar_convite
from .models import ConviteEscritorio, Escritorio, MembroEscritorio
from .tokens import gerar_token, hash_token


PAPEIS_GESTORES = {
    MembroEscritorio.Papel.OWNER,
    MembroEscritorio.Papel.ADMIN,
}

# Proprietário não se concede por convite: a transferência de propriedade passa
# por `atualizar_membro`, que protege o último proprietário ativo.
PAPEIS_CONVIDAVEIS = {
    MembroEscritorio.Papel.ADMIN,
    MembroEscritorio.Papel.ADVOGADO,
    MembroEscritorio.Papel.ESTAGIARIO,
}


def _exigir_gestor(membro_ator):
    if (
        membro_ator.status != MembroEscritorio.Status.ATIVO
        or membro_ator.papel not in PAPEIS_GESTORES
    ):
        raise PermissionDenied("Somente proprietários e administradores podem gerenciar o escritório.")


@transaction.atomic
def atualizar_escritorio(*, escritorio, membro_ator, dados):
    _exigir_gestor(membro_ator)
    if membro_ator.escritorio_id != escritorio.id:
        raise PermissionDenied("Escritório indisponível para este usuário.")

    escritorio = Escritorio.objects.select_for_update().get(pk=escritorio.pk)
    campos = []
    for campo in ("nome", "fuso_horario"):
        if campo in dados and getattr(escritorio, campo) != dados[campo]:
            setattr(escritorio, campo, dados[campo])
            campos.append(campo)

    if campos:
        escritorio.save(update_fields=(*campos, "atualizado_em"))
        registrar_evento_auditoria(
            escritorio=escritorio,
            ator=membro_ator.usuario,
            acao="escritorio.atualizado",
            recurso_tipo="escritorio",
            recurso_id=escritorio.pk,
            alteracoes={"campos": campos},
        )
    return escritorio


@transaction.atomic
def atualizar_membro(*, membro, membro_ator, papel=None, status=None):
    _exigir_gestor(membro_ator)
    if membro_ator.escritorio_id != membro.escritorio_id:
        raise PermissionDenied("Membro indisponível para este usuário.")

    membros = list(
        MembroEscritorio.objects.select_for_update().filter(
            escritorio_id=membro.escritorio_id
        )
    )
    membro = next(item for item in membros if item.pk == membro.pk)

    novo_papel = papel if papel is not None else membro.papel
    novo_status = status if status is not None else membro.status
    remove_owner_ativo = (
        membro.papel == MembroEscritorio.Papel.OWNER
        and membro.status == MembroEscritorio.Status.ATIVO
        and (
            novo_papel != MembroEscritorio.Papel.OWNER
            or novo_status != MembroEscritorio.Status.ATIVO
        )
    )
    if remove_owner_ativo:
        owners_ativos = sum(
            item.papel == MembroEscritorio.Papel.OWNER
            and item.status == MembroEscritorio.Status.ATIVO
            for item in membros
        )
        if owners_ativos <= 1:
            raise ValidationError(
                {"detail": "O último proprietário ativo não pode ser rebaixado ou suspenso."}
            )

    campos = []
    alteracoes = {}
    if novo_papel != membro.papel:
        alteracoes["papel"] = {"anterior": membro.papel, "novo": novo_papel}
        membro.papel = novo_papel
        campos.append("papel")
    if novo_status != membro.status:
        alteracoes["status"] = {"anterior": membro.status, "novo": novo_status}
        membro.status = novo_status
        campos.append("status")

    if campos:
        membro.save(update_fields=(*campos, "atualizado_em"))
        registrar_evento_auditoria(
            escritorio=membro.escritorio,
            ator=membro_ator.usuario,
            acao="membro.atualizado",
            recurso_tipo="membro_escritorio",
            recurso_id=membro.pk,
            alteracoes=alteracoes,
        )
    return membro



@transaction.atomic
def convidar_membro(*, escritorio, membro_ator, email, papel, enviar=enviar_convite):
    """Cria o convite e envia o link depois do commit.

    `enviar` é injetável: o service não depende de SMTP, e o teste troca o envio
    sem precisar de patch.
    """
    _exigir_gestor(membro_ator)
    if membro_ator.escritorio_id != escritorio.id:
        raise PermissionDenied("Escritório indisponível para este usuário.")
    if papel not in PAPEIS_CONVIDAVEIS:
        raise ValidationError({"papel": "Este papel não pode ser atribuído por convite."})

    email = email.strip().lower()
    if MembroEscritorio.objects.filter(
        escritorio=escritorio, usuario__email__iexact=email
    ).exists():
        raise ValidationError({"email": "Esta pessoa já faz parte do escritório."})

    # Reenviar substitui o convite anterior: o link antigo deixa de valer.
    ConviteEscritorio.objects.filter(
        escritorio=escritorio, email=email, aceito_em__isnull=True
    ).delete()

    token = gerar_token()
    convite = ConviteEscritorio.objects.create(
        escritorio=escritorio,
        email=email,
        papel=papel,
        token_hash=hash_token(token),
        convidado_por=membro_ator.usuario,
        expira_em=timezone.now() + timedelta(days=settings.CONVITE_VALIDADE_DIAS),
    )
    registrar_evento_auditoria(
        escritorio=escritorio,
        ator=membro_ator.usuario,
        acao="convite.criado",
        recurso_tipo="convite_escritorio",
        recurso_id=convite.pk,
        alteracoes={"email": email, "papel": papel},
    )
    transaction.on_commit(lambda: enviar(convite=convite, token=token))
    return convite


@transaction.atomic
def revogar_convite(*, convite, membro_ator):
    _exigir_gestor(membro_ator)
    if membro_ator.escritorio_id != convite.escritorio_id:
        raise PermissionDenied("Convite indisponível para este usuário.")
    if convite.aceito_em:
        raise ValidationError({"detail": "Este convite já foi aceito."})

    registrar_evento_auditoria(
        escritorio=convite.escritorio,
        ator=membro_ator.usuario,
        acao="convite.revogado",
        recurso_tipo="convite_escritorio",
        recurso_id=convite.pk,
        alteracoes={"email": convite.email},
    )
    convite.delete()
