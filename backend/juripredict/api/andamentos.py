"""Acompanhamento automático de processos: lê os movimentos no DataJud e guarda.

Mesmo molde de ``lembretes``: sem fila, o comando ``sincronizar_andamentos`` roda
em qualquer agendador e cada processo é isolado dos demais. A leitura (``buscar``)
é injetável, então o serviço não conhece a rede.
"""

import logging
from collections import defaultdict

from django.db.models import F, Max
from django.utils import timezone

from .datajud import DatajudErro, consultar_movimentos
from .emails import enviar_novos_andamentos
from .lembretes import _ainda_e_membro_ativo
from .models import Andamento, Processo

logger = logging.getLogger(__name__)


def sincronizar_processo(processo, *, buscar=consultar_movimentos):
    """Grava os movimentos ainda não conhecidos e devolve quantos eram novos.

    Se a leitura falhar nada é marcado como sincronizado: a próxima rodada tenta
    de novo, e o processo continua na frente da fila.
    """
    movimentos = buscar(processo.numero_cnj)
    antes = processo.andamentos.count()
    # A restrição de unicidade não cobre movimento sem código: para o banco, NULL nunca é
    # igual a NULL, e cada leitura duplicaria o movimento.
    conhecidos = set(processo.andamentos.values_list("data_hora", "codigo", "nome"))
    ineditos = []
    for movimento in movimentos:
        chave = (movimento["data_hora"], movimento["codigo"], movimento["nome"])
        if chave not in conhecidos:
            conhecidos.add(chave)
            ineditos.append(Andamento(processo=processo, **movimento))
    Andamento.objects.bulk_create(ineditos, ignore_conflicts=True)
    # update(): marcar a leitura não deve mexer em `atualizado_em`, que ordena a lista.
    Processo.objects.filter(pk=processo.pk).update(andamentos_sincronizados_em=timezone.now())
    return processo.andamentos.count() - antes


def sincronizar_todos(*, limite=200, buscar=consultar_movimentos, avisar=enviar_novos_andamentos):
    """Sincroniza os processos ativos, os há mais tempo sem leitura primeiro.

    ``limite`` evita uma rodada interminável com muitos processos; o que ficou
    de fora vem na frente da fila na rodada seguinte. Quem cadastrou o processo
    recebe um e-mail com o que há de novo, num só e-mail por escritório.
    """
    processos = (
        Processo.objects.filter(status="ATIVO", escritorio__ativo=True)
        .select_related("usuario", "escritorio")
        .order_by(F("andamentos_sincronizados_em").asc(nulls_first=True), "pk")[:limite]
    )
    resumo = {"processos": 0, "novos": 0, "falhas": 0, "avisados": 0}
    avisos = defaultdict(list)
    for processo in processos:
        # Na primeira leitura tudo é "novo": o histórico inteiro não é novidade.
        ja_lido = processo.andamentos_sincronizados_em is not None
        ultimo_id = processo.andamentos.aggregate(Max("id"))["id__max"] or 0
        try:
            novos = sincronizar_processo(processo, buscar=buscar)
        except DatajudErro as exc:
            resumo["falhas"] += 1
            logger.warning("Processo %s não sincronizado: %s", processo.pk, exc)
            continue
        except Exception:
            resumo["falhas"] += 1
            logger.exception("Falha inesperada ao sincronizar o processo %s", processo.pk)
            continue
        resumo["novos"] += novos
        resumo["processos"] += 1
        if novos and ja_lido and processo.usuario_id:
            achados = list(processo.andamentos.filter(id__gt=ultimo_id).order_by("data_hora"))
            avisos[(processo.usuario, processo.escritorio)].append((processo, achados))

    membros = {}
    for (usuario, escritorio), itens in avisos.items():
        if not usuario.is_active or not usuario.email:
            continue
        # quem saiu do escritório não deve receber o que acontece nele
        if not _ainda_e_membro_ativo(usuario.pk, escritorio.pk, membros):
            continue
        try:
            avisar(usuario=usuario, escritorio=escritorio, itens=itens)
            resumo["avisados"] += 1
        except Exception:  # falha de e-mail não desfaz a leitura já gravada
            logger.exception("Falha ao avisar o usuário %s sobre andamentos", usuario.pk)
    return resumo
