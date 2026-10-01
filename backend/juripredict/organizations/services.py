from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from auditlog.services import registrar_evento_auditoria

from .models import Escritorio, MembroEscritorio


PAPEIS_GESTORES = {
    MembroEscritorio.Papel.OWNER,
    MembroEscritorio.Papel.ADMIN,
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

