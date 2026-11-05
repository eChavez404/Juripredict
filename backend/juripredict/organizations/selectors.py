import uuid

from django.utils import timezone

from .models import ConviteEscritorio, MembroEscritorio
from .tokens import hash_token


class ContextoEscritorioInvalido(Exception):
    pass


class ContextoEscritorioAusente(Exception):
    pass


def memberships_do_usuario(usuario, *, incluir_suspensos=False):
    queryset = MembroEscritorio.objects.filter(usuario=usuario).select_related(
        "escritorio", "usuario"
    )
    if not incluir_suspensos:
        queryset = queryset.filter(
            status=MembroEscritorio.Status.ATIVO,
            escritorio__ativo=True,
        )
    return queryset


def resolver_membership(usuario, escritorio_id=None, *, obrigatorio=True):
    memberships = memberships_do_usuario(usuario)

    if escritorio_id:
        try:
            escritorio_uuid = uuid.UUID(str(escritorio_id))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ContextoEscritorioInvalido("Identificador de escritório inválido.") from exc

        membro = memberships.filter(escritorio_id=escritorio_uuid).first()
        if not membro:
            raise ContextoEscritorioInvalido("Escritório indisponível para este usuário.")
        return membro

    encontrados = list(memberships[:2])
    if len(encontrados) == 1:
        return encontrados[0]
    if obrigatorio:
        raise ContextoEscritorioAusente(
            "Informe X-Escritorio-ID quando não houver exatamente um escritório ativo."
        )
    return None



def convites_pendentes_do_escritorio(escritorio):
    return ConviteEscritorio.objects.filter(
        escritorio=escritorio, aceito_em__isnull=True
    )


def convite_pendente_por_token(token, *, bloquear=False):
    """Convite ainda válido para o token, ou ``None``.

    Expirado e já aceito são tratados igual a inexistente: quem chama não deve
    conseguir distinguir os casos pela resposta.
    """
    queryset = ConviteEscritorio.objects.select_related("escritorio")
    if bloquear:
        queryset = queryset.select_for_update()
    return queryset.filter(
        token_hash=hash_token(token),
        aceito_em__isnull=True,
        expira_em__gt=timezone.now(),
        escritorio__ativo=True,
    ).first()
