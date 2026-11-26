"""Estudo de caso: a conversa do advogado com o agente de IA, guardada no escritório.

Cada mensagem do advogado acrescenta ao caso, e o agente refaz a análise do caso inteiro, para
mostrar o que a informação nova mudou. O agente não guarda nada: recebe o caso consolidado a cada
vez e devolve a análise, que fica aqui. O id do job nunca sai para o navegador.
"""

import html
import logging
import re
import zipfile
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.exceptions import NotFound, ValidationError

from auditlog.services import registrar_evento_auditoria

from . import agente
from .models import MensagemCaso

logger = logging.getLogger(__name__)

# O mesmo teto do agente (CaseRequest.relato): acima disso o caso precisa ser resumido.
LIMITE_RELATO = 20000
# Quanto do relato o processo vinculado pode ocupar; o resto fica para a conversa.
LIMITE_PROCESSO = 8000
PAGINAS_PDF = 30
# O XML do DOCX é lido só até aqui: um zip pequeno pode descompactar em gigabytes.
LIMITE_XML_DOCX = 5 * 1024 * 1024
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


def texto_do_arquivo(arquivo):
    """O texto de um PDF ou DOCX. DOC antigo e PDF só de imagem (digitalizado) voltam vazios."""
    extensao = arquivo.name.rsplit(".", 1)[-1].lower()
    try:
        with arquivo.open("rb") as conteudo:
            if extensao == "pdf":
                paginas = PdfReader(conteudo).pages[:PAGINAS_PDF]
                return "\n".join(pagina.extract_text() or "" for pagina in paginas).strip()
            if extensao == "docx":
                with zipfile.ZipFile(conteudo) as docx, docx.open("word/document.xml") as xml:
                    corpo = xml.read(LIMITE_XML_DOCX).decode("utf-8", "ignore")
                paragrafos = corpo.split("</w:p>")
                return "\n".join(
                    html.unescape("".join(re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", p)))
                    for p in paragrafos
                ).strip()
    except Exception as exc:  # arquivo enviado pelo usuário: corrompido não derruba a análise
        logger.warning("documento_ilegivel extensao=%s causa=%s", extensao, type(exc).__name__)
    return ""


def contexto_do_processo(processo, espaco):
    """O cadastro do processo e o texto dos documentos, em até `espaco` caracteres.

    Ficam de fora cliente, parte contrária, título, valor da causa e o nome dos arquivos, que
    costumam trazer nomes. Os dados pessoais do texto são mascarados no agente, antes da IA.
    Devolve também a situação de cada documento, para a tela mostrar o que a análise leu.
    """
    espaco = min(espaco, LIMITE_PROCESSO)
    texto = (
        f"Processo vinculado, do cadastro do escritório: área {processo.get_area_display().lower()}, "
        f"{processo.vara}, comarca de {processo.comarca}, situação {processo.get_status_display().lower()}"
        + (f", distribuído em {processo.data_distribuicao:%d/%m/%Y}" if processo.data_distribuicao else "")
        + "."
    )
    if processo.observacoes:
        texto += f"\nObservações do processo: {processo.observacoes}"
    arquivos = [(d.nome, d.arquivo) for d in processo.documentos.all()]
    if processo.arquivo_peticao_inicial:
        arquivos.append(("Petição inicial", processo.arquivo_peticao_inicial))
    lidos = []
    for numero, (nome, arquivo) in enumerate(arquivos, start=1):
        cabecalho = f"\n\nDocumento {numero} do processo:\n"
        sobra = espaco - len(texto) - len(cabecalho)
        conteudo = texto_do_arquivo(arquivo) if sobra >= 200 else None
        if conteudo is None:
            situacao = "fora do limite"
        elif not conteudo:
            situacao = "sem texto"
        else:
            texto += cabecalho + conteudo[:sobra]
            situacao = "lido" if len(conteudo) <= sobra else "lido em parte"
        lidos.append({"nome": nome, "situacao": situacao})
    return texto[:espaco], lidos


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
    documentos_lidos = []
    if caso.processo:
        contexto, documentos_lidos = contexto_do_processo(caso.processo, LIMITE_RELATO - len(relato) - 2)
        relato = f"{relato}\n\n{contexto}"
    with transaction.atomic():
        MensagemCaso.objects.create(
            caso=caso, autor=MensagemCaso.Autor.ADVOGADO, texto=texto, documentos_lidos=documentos_lidos
        )
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
            alteracoes={"tema": caso.tema, "fase": caso.fase, "processo": caso.processo_id},
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
