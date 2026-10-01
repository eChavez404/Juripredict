from collections.abc import Mapping, Sequence

from .models import EventoAuditoria


CHAVES_SENSIVEIS = {
    "access",
    "arquivo",
    "authorization",
    "cpf",
    "cpf_cnpj",
    "cpf_cnpj_hash",
    "documento",
    "password",
    "refresh",
    "senha",
    "token",
}


def _chave_sensivel(chave):
    normalizada = str(chave).lower()
    return any(item in normalizada for item in CHAVES_SENSIVEIS)


def sanitizar(valor):
    if isinstance(valor, Mapping):
        return {
            str(chave): "[REMOVIDO]" if _chave_sensivel(chave) else sanitizar(item)
            for chave, item in valor.items()
        }
    if isinstance(valor, Sequence) and not isinstance(valor, (str, bytes, bytearray)):
        return [sanitizar(item) for item in valor]
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def registrar_evento_auditoria(
    *, escritorio, ator, acao, recurso_tipo, recurso_id, alteracoes=None
):
    return EventoAuditoria.objects.create(
        escritorio=escritorio,
        ator=ator,
        acao=acao,
        recurso_tipo=recurso_tipo,
        recurso_id=str(recurso_id),
        alteracoes=sanitizar(alteracoes or {}),
    )

