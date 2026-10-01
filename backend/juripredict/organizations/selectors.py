import uuid

from .models import MembroEscritorio


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

