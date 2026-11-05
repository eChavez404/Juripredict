"""Anexos de processo: validação de limite, gravação, exclusão e auditoria.

O conteúdo do arquivo (tipo e tamanho) é validado no serializer; aqui ficam as
regras do processo: quantos anexos cabem e quem fez o quê.
"""

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from auditlog.services import registrar_evento_auditoria

from .models import DocumentoProcesso


@transaction.atomic
def anexar_documento(*, processo, arquivo, usuario):
    # Trava o processo: dois envios simultâneos não podem furar o limite juntos.
    processo = type(processo).objects.select_for_update().get(pk=processo.pk)
    if processo.documentos.count() >= settings.DOCUMENTOS_MAX_POR_PROCESSO:
        raise ValidationError(
            {"arquivo": [f"Cada processo aceita até {settings.DOCUMENTOS_MAX_POR_PROCESSO} documentos."]}
        )
    documento = DocumentoProcesso.objects.create(
        processo=processo,
        arquivo=arquivo,
        nome=(arquivo.name or "documento")[-255:],
        tamanho=arquivo.size,
        enviado_por=usuario,
    )
    registrar_evento_auditoria(
        escritorio=processo.escritorio,
        ator=usuario,
        acao="processo.documento_anexado",
        recurso_tipo="processo",
        recurso_id=processo.pk,
        # não chamar de "documento"/"arquivo": o sanitizador do log apaga essas chaves
        alteracoes={"nome_do_anexo": documento.nome},
    )
    return documento


@transaction.atomic
def remover_documento(*, documento, usuario):
    processo = documento.processo
    nome = documento.nome
    documento.delete()
    registrar_evento_auditoria(
        escritorio=processo.escritorio,
        ator=usuario,
        acao="processo.documento_removido",
        recurso_tipo="processo",
        recurso_id=processo.pk,
        alteracoes={"nome_do_anexo": nome},
    )
