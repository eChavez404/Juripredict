"""Lembretes de prazo e audiência por e-mail.

Sem Celery nem fila: o comando ``enviar_lembretes`` é chamado de hora em hora por
qualquer agendador (cron, Render Cron Job). Cada evento é marcado só depois que o
e-mail sai, então uma falha de envio é refeita na execução seguinte.
"""

import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from organizations.models import MembroEscritorio

from .emails import enviar_lembrete_prazos
from .models import EventoAgenda

logger = logging.getLogger(__name__)

TIPOS_COM_LEMBRETE = ("PRAZO", "AUDIENCIA")

# Tolerância para o que já começou: se o agendador ficar algumas horas fora do ar,
# o aviso ainda sai quando ele voltar. Além disso o evento é considerado passado.
TOLERANCIA_ATRASO = timedelta(hours=6)


def eventos_para_lembrar(*, agora, antecedencia):
    return (
        EventoAgenda.objects.filter(
            tipo__in=TIPOS_COM_LEMBRETE,
            concluido=False,
            lembrete_enviado_em__isnull=True,
            inicio__gte=agora - TOLERANCIA_ATRASO,
            inicio__lte=agora + antecedencia,
            escritorio__ativo=True,
            usuario__is_active=True,
            usuario__isnull=False,
        )
        .exclude(usuario__email="")
        .select_related("usuario", "escritorio", "processo")
        .order_by("inicio")
    )


def _ainda_e_membro_ativo(usuario_id, escritorio_id, cache):
    chave = (usuario_id, escritorio_id)
    if chave not in cache:
        cache[chave] = MembroEscritorio.objects.filter(
            usuario_id=usuario_id,
            escritorio_id=escritorio_id,
            status=MembroEscritorio.Status.ATIVO,
        ).exists()
    return cache[chave]


def enviar_lembretes(*, agora=None, antecedencia=None, enviar=enviar_lembrete_prazos):
    """Envia os lembretes pendentes e devolve quantos eventos foram avisados.

    `enviar` é injetável, como nos services de ``organizations``.
    """
    agora = agora or timezone.now()
    antecedencia = antecedencia or timedelta(hours=settings.LEMBRETE_ANTECEDENCIA_HORAS)

    grupos = defaultdict(list)
    membros = {}
    for evento in eventos_para_lembrar(agora=agora, antecedencia=antecedencia):
        # quem saiu do escritório não deve receber a agenda dele
        if _ainda_e_membro_ativo(evento.usuario_id, evento.escritorio_id, membros):
            grupos[(evento.usuario, evento.escritorio)].append(evento)

    avisados = 0
    for (usuario, escritorio), eventos in grupos.items():
        try:
            enviar(usuario=usuario, escritorio=escritorio, eventos=eventos)
        except Exception:  # um destinatário com problema não pode travar os demais
            logger.exception("Falha ao enviar lembrete para o usuário %s", usuario.pk)
            continue
        EventoAgenda.objects.filter(pk__in=[e.pk for e in eventos]).update(
            lembrete_enviado_em=agora
        )
        avisados += len(eventos)
    return avisados
