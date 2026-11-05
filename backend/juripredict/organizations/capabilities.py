from .models import MembroEscritorio


# Tabela única dos papéis: para mudar quem pode o quê, é aqui. O backend aplica estas
# capabilities (serializers e views) e o frontend as usa para esconder o que a pessoa não
# pode usar; vale igualmente para tokens de API, que herdam o papel da pessoa.
CAPABILITIES_COMUNS = frozenset(
    {
        "escritorio.ler",
        "membros.ler",
        "clientes.gerenciar",
        "processos.gerenciar",
        "agenda.gerenciar",
    }
)

# O que o estagiário NÃO tem, por padrão: o valor da causa, a jurimetria da carteira, o
# CPF/CNPJ completo dos clientes (vê mascarado e não o altera) e a exclusão de processos e
# clientes. Os demais papéis têm tudo isso.
CAPABILITIES_DE_ADVOGADO = CAPABILITIES_COMUNS | {
    "processos.valores.ler",
    "jurimetria.ler",
    "clientes.documento.ler",
    "processos.excluir",
    "clientes.excluir",
}

CAPABILITIES_POR_PAPEL = {
    MembroEscritorio.Papel.OWNER: CAPABILITIES_DE_ADVOGADO
    | {"escritorio.editar", "membros.gerenciar", "auditoria.ler"},
    MembroEscritorio.Papel.ADMIN: CAPABILITIES_DE_ADVOGADO
    | {"escritorio.editar", "membros.gerenciar", "auditoria.ler"},
    MembroEscritorio.Papel.ADVOGADO: CAPABILITIES_DE_ADVOGADO,
    MembroEscritorio.Papel.ESTAGIARIO: CAPABILITIES_COMUNS,
}


def capabilities_do_membro(membro):
    if not membro or membro.status != MembroEscritorio.Status.ATIVO:
        return []
    return sorted(CAPABILITIES_POR_PAPEL.get(membro.papel, frozenset()))


def request_tem_capability(request, capability):
    """A pessoa da requisição tem a capability no escritório informado?

    Sem escritório válido, não tem: não existe papel fora de um escritório.
    """
    from .context import contexto_escritorio_da_request

    membro = contexto_escritorio_da_request(request, obrigatorio=False)
    return capability in capabilities_do_membro(membro)
