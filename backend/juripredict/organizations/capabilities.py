from .models import MembroEscritorio


CAPABILITIES_COMUNS = frozenset(
    {
        "escritorio.ler",
        "membros.ler",
        "clientes.gerenciar",
        "processos.gerenciar",
        "agenda.gerenciar",
    }
)

CAPABILITIES_POR_PAPEL = {
    MembroEscritorio.Papel.OWNER: CAPABILITIES_COMUNS
    | {"escritorio.editar", "membros.gerenciar", "auditoria.ler"},
    MembroEscritorio.Papel.ADMIN: CAPABILITIES_COMUNS
    | {"escritorio.editar", "membros.gerenciar", "auditoria.ler"},
    MembroEscritorio.Papel.ADVOGADO: CAPABILITIES_COMUNS,
    MembroEscritorio.Papel.ESTAGIARIO: CAPABILITIES_COMUNS,
}


def capabilities_do_membro(membro):
    if not membro or membro.status != MembroEscritorio.Status.ATIVO:
        return []
    return sorted(CAPABILITIES_POR_PAPEL.get(membro.papel, frozenset()))

