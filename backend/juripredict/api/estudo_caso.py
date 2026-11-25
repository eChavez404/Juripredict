"""Estudo de caso: a conversa do advogado com o agente de IA, guardada no escritório.

Cada mensagem do advogado acrescenta ao caso, e o agente refaz a análise do caso inteiro, para
mostrar o que a informação nova mudou. O agente não guarda nada: recebe o caso consolidado a cada
vez e devolve a análise, que fica aqui. O id do job nunca sai para o navegador.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from auditlog.services import registrar_evento_auditoria

from . import agente
from .models import MensagemCaso

# O mesmo teto do agente (CaseRequest.relato): acima disso o caso precisa ser resumido.
LIMITE_RELATO = 20000
# Acima do pior caso do agente (busca, duas tentativas com repetição): depois disso, desiste.
ESPERA_MAXIMA = timedelta(minutes=10)
PERDIDA = "A análise se perdeu (o agente reiniciou). Envie a mensagem de novo."
DEMOROU = "A análise demorou demais. Envie a mensagem de novo."


def relato_consolidado(caso, nova=None):
    """O relato inicial e o que o advogado acrescentou depois, em ordem."""
    textos = [m.texto for m in caso.mensagens.filter(autor=MensagemCaso.Autor.ADVOGADO).order_by("criado_em", "id")]
    if nova:
        textos.append(nova)
    partes = [textos[0], *(f"Informação acrescentada pelo advogado: {t}" for t in textos[1:])]
    relato = "\n\n".join(partes)
    if len(relato) > LIMITE_RELATO:
        raise ValidationError(
            {"texto": ["O caso passou de 20 mil caracteres. Abra um caso novo com o relato resumido."]}
        )
    return relato


def _pedido(caso, relato, mensagem=None):
    return {
        "tema": caso.tema,
        "fase": caso.fase,
        "relato": relato,
        "provas": caso.provas,
        "orgao_julgador": caso.orgao_julgador,
        "mensagem": mensagem,
    }


def enviar(caso, texto, usuario, *, primeira=False):
    """Grava a mensagem do advogado e pede a análise. Se o agente recusar, nada é gravado."""
    if caso.mensagens.filter(status=MensagemCaso.Status.PENDENTE).exists():
        raise ValidationError({"texto": ["Aguarde a análise em andamento terminar."]})
    relato = relato_consolidado(caso, texto)
    with transaction.atomic():
        MensagemCaso.objects.create(caso=caso, autor=MensagemCaso.Autor.ADVOGADO, texto=texto)
        job_id, _ = agente.iniciar(_pedido(caso, relato, None if primeira else texto))
        MensagemCaso.objects.create(
            caso=caso, autor=MensagemCaso.Autor.AGENTE, status=MensagemCaso.Status.PENDENTE, job_id=job_id
        )
        caso.save(update_fields=["atualizado_em"])
        registrar_evento_auditoria(
            escritorio=caso.escritorio,
            ator=usuario,
            acao="agente.caso_criado" if primeira else "agente.mensagem_enviada",
            recurso_tipo="caso_estudo",
            recurso_id=caso.pk,
            alteracoes={"tema": caso.tema, "fase": caso.fase},
        )


def atualizar_pendente(caso):
    """Consulta o agente sobre a análise em andamento e grava o resultado quando ela termina.

    Devolve a etapa em que o agente está, para a tela mostrar o andamento.
    """
    pendente = caso.mensagens.filter(status=MensagemCaso.Status.PENDENTE).first()
    if pendente is None:
        return None
    try:
        analise = agente.consultar(pendente.job_id)
    except NotFound:
        analise = {"status": "error", "error": PERDIDA}
    except agente.AgenteIndisponivel:
        # passageiro (agente ligando, por exemplo); só desiste depois da espera máxima
        analise = {"status": "running", "step": None}
    if analise["status"] == "running" and timezone.now() - pendente.criado_em > ESPERA_MAXIMA:
        analise = {"status": "error", "error": DEMOROU}
    if analise["status"] == "running":
        return analise.get("step")

    if analise["status"] == "done" and analise.get("result"):
        resultado = analise["result"]
        medicao = resultado["medicao"]
        pendente.texto = resultado["analise"]["resposta"]
        pendente.resultado = resultado
        pendente.indice_atual = medicao["indice_atual"]
        pendente.indice_potencial = medicao["indice_potencial"]
        pendente.status = MensagemCaso.Status.CONCLUIDA
        if not caso.titulo:
            caso.titulo = resultado["analise"]["titulo"][:120]
            caso.save(update_fields=["titulo", "atualizado_em"])
    else:
        pendente.status = MensagemCaso.Status.ERRO
        pendente.erro = (analise.get("error") or "Não foi possível analisar o caso.")[:300]
    pendente.job_id = ""
    pendente.save()
    return None
