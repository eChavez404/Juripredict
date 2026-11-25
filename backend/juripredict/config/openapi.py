"""Peças da documentação OpenAPI: nada aqui participa do tratamento das requisições.

Estes serializers só descrevem respostas montadas à mão nas views. O teste
``api.test_openapi`` falha se a resposta real deixar de bater com eles.
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import serializers

from api.serializers import (
    AndamentoRecenteSerializer,
    AndamentoSerializer,
    EventoAgendaSerializer,
    ProcessoResumoSerializer,
    ProcessoSerializer,
    UsuarioSerializer,
)


class TokenApiScheme(OpenApiAuthenticationExtension):
    target_class = "accounts.authentication.TokenApiAuthentication"
    name = "tokenApi"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "Token de API (jp_...): somente GET, em uma lista fixa de rotas.",
        }


def adicionar_cabecalho_escritorio(result, generator, request, public):
    """Pós-processamento: documenta o X-Escritorio-ID nas rotas que dependem do escritório."""
    parametro = {
        "in": "header",
        "name": "X-Escritorio-ID",
        "schema": {"type": "string", "format": "uuid"},
        "description": "Escritório ativo. Obrigatório quando o usuário pertence a mais de um.",
    }
    for caminho, operacoes in result["paths"].items():
        if caminho.startswith("/api/v1/auth/") and caminho != "/api/v1/auth/me/":
            continue
        for operacao in operacoes.values():
            operacao.setdefault("parameters", []).append(parametro)
    return result


class DetalheSerializer(serializers.Serializer):
    detail = serializers.CharField()


class SessaoSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UsuarioSerializer()


class TokenApiCriadoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nome = serializers.CharField()
    prefixo = serializers.CharField()
    criado_em = serializers.DateTimeField()
    expira_em = serializers.DateTimeField()
    ultimo_uso_em = serializers.DateTimeField(allow_null=True)
    revogado_em = serializers.DateTimeField(allow_null=True)
    ativo = serializers.BooleanField()
    token = serializers.CharField(help_text="Exibido uma única vez; no banco fica só o hash.")


class AndamentosRespostaSerializer(serializers.Serializer):
    sincronizado_em = serializers.DateTimeField(allow_null=True)
    andamentos = AndamentoSerializer(many=True)


class SincronizacaoRespostaSerializer(AndamentosRespostaSerializer):
    novos = serializers.IntegerField()


class NomeValorSerializer(serializers.Serializer):
    name = serializers.CharField()
    value = serializers.IntegerField()


class IntervaloSerializer(serializers.Serializer):
    min = serializers.IntegerField()
    max = serializers.IntegerField()


class TaxaPorVaraSerializer(serializers.Serializer):
    vara = serializers.CharField()
    total = serializers.IntegerField()
    suficiente = serializers.BooleanField()
    favoravel = serializers.IntegerField(allow_null=True)
    desfavoravel = serializers.IntegerField(allow_null=True)
    intervalo_favoravel = IntervaloSerializer(allow_null=True)
    motivo = serializers.CharField(allow_null=True)


class TaxaPorAnoSerializer(serializers.Serializer):
    ano = serializers.IntegerField(allow_null=True, help_text="Nulo: processos sem data de distribuição.")
    total = serializers.IntegerField()
    suficiente = serializers.BooleanField()
    favoravel = serializers.IntegerField(allow_null=True)
    desfavoravel = serializers.IntegerField(allow_null=True)
    intervalo_favoravel = IntervaloSerializer(allow_null=True)
    motivo = serializers.CharField(allow_null=True)


class FiltrosAplicadosSerializer(serializers.Serializer):
    area = serializers.CharField(allow_null=True)
    ano = serializers.CharField(allow_null=True)


class OpcaoDeAreaSerializer(serializers.Serializer):
    valor = serializers.CharField()
    rotulo = serializers.CharField()


class OpcoesDeFiltroSerializer(serializers.Serializer):
    areas = OpcaoDeAreaSerializer(many=True)
    anos = serializers.ListField(child=serializers.IntegerField())


class JurimetriaProcessosRespostaSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    exibidos = serializers.IntegerField(help_text="A lista é cortada em 200 itens.")
    processos = ProcessoResumoSerializer(many=True)


class DiaDaMemoriaSerializer(serializers.Serializer):
    data = serializers.DateField()
    motivo = serializers.CharField()


class PrazoCalculoRespostaSerializer(serializers.Serializer):
    data_base = serializers.DateField()
    dias = serializers.IntegerField()
    tipo = serializers.CharField()
    area = serializers.CharField()
    fundamento = serializers.CharField()
    marco_inicial = serializers.DateField()
    primeiro_dia_contado = serializers.DateField()
    vencimento = serializers.DateField()
    fins_de_semana_nao_contados = serializers.IntegerField()
    dias_nao_contados = DiaDaMemoriaSerializer(many=True)
    dias_a_conferir = DiaDaMemoriaSerializer(
        many=True, help_text="Contados como úteis; dependem do calendário do tribunal."
    )
    ressalvas = serializers.ListField(child=serializers.CharField())


class AgenteOpcaoSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class AgenteOpcoesRespostaSerializer(serializers.Serializer):
    ia_configurada = serializers.BooleanField(help_text="Há chave; não diz se ela funciona.")
    base_configurada = serializers.BooleanField(help_text="Há chave e índice do Pinecone.")
    temas = AgenteOpcaoSerializer(many=True)
    fases = AgenteOpcaoSerializer(many=True)
    provas = AgenteOpcaoSerializer(many=True)


class AgenteAnaliseRespostaSerializer(serializers.Serializer):
    id = serializers.CharField(help_text="Vale só para quem pediu, no mesmo escritório.")
    status = serializers.CharField(help_text="running, done ou error.")
    step = serializers.CharField(allow_null=True, help_text="Etapa em andamento.")
    result = serializers.DictField(
        allow_null=True, help_text="Contrato em agente/app/agents/analista/schema.py."
    )
    error = serializers.CharField(allow_null=True)


class PendenciasRespostaSerializer(serializers.Serializer):
    urgentes = serializers.IntegerField(help_text="Prazos vencidos e compromissos até amanhã.")
    total_vencidos = serializers.IntegerField()
    total_proximos = serializers.IntegerField()
    vencidos = EventoAgendaSerializer(many=True)
    proximos = EventoAgendaSerializer(many=True)
    andamentos_recentes = AndamentoRecenteSerializer(many=True)


class JurimetriaRespostaSerializer(serializers.Serializer):
    total_analisados = serializers.IntegerField()
    taxa_favoravel = serializers.IntegerField(
        allow_null=True, help_text="Nula abaixo do piso de amostra."
    )
    intervalo_favoravel = IntervaloSerializer(
        allow_null=True, help_text="Intervalo de confiança de 95% (Wilson)."
    )
    amostra_suficiente = serializers.BooleanField()
    piso_amostra = serializers.IntegerField()
    processos_ativos = serializers.IntegerField()
    por_vara = TaxaPorVaraSerializer(many=True)
    por_ano = TaxaPorAnoSerializer(many=True)
    resultados = NomeValorSerializer(many=True)
    filtros = FiltrosAplicadosSerializer()
    opcoes = OpcoesDeFiltroSerializer()
    insight = serializers.CharField()


class TaxaTribunalSerializer(serializers.Serializer):
    total = serializers.IntegerField(help_text="Decisões de mérito com resultado no recorte.")
    suficiente = serializers.BooleanField()
    favoravel = serializers.IntegerField(allow_null=True, help_text="Taxa de deferimento; nula se suprimida.")
    desfavoravel = serializers.IntegerField(allow_null=True)
    intervalo_favoravel = IntervaloSerializer(allow_null=True)
    motivo = serializers.CharField(allow_null=True, help_text="Por que a taxa foi suprimida.")
    cobertura = serializers.IntegerField(allow_null=True, help_text="Cobertura da fonte, em %.")


class TaxaTribunalPorVaraSerializer(TaxaTribunalSerializer):
    vara = serializers.CharField()


class TaxaTribunalPorAnoSerializer(TaxaTribunalSerializer):
    ano = serializers.IntegerField()


class ForaDaTaxaSerializer(serializers.Serializer):
    motivo = serializers.CharField()
    total = serializers.IntegerField()


class ValidacaoTribunalSerializer(serializers.Serializer):
    rotulo_conferido = serializers.BooleanField()
    motivo = serializers.CharField(allow_null=True)
    gold_set = serializers.DictField(allow_null=True)
    cobertura_medida = serializers.BooleanField()


class OpcoesTribunalSerializer(serializers.Serializer):
    temas = OpcaoDeAreaSerializer(many=True)
    varas = serializers.ListField(child=serializers.CharField())
    anos = serializers.ListField(child=serializers.IntegerField())


class FonteTribunalSerializer(serializers.Serializer):
    origem = serializers.CharField()
    inicio = serializers.DateField(allow_null=True)
    fim = serializers.DateField(allow_null=True)
    versao = serializers.CharField()
    importado_em = serializers.DateTimeField()


class FiltrosTribunalSerializer(serializers.Serializer):
    tema = serializers.CharField()
    vara = serializers.CharField(required=False)
    ano = serializers.IntegerField(required=False)


class JurimetriaTribunalRespostaSerializer(serializers.Serializer):
    disponivel = serializers.BooleanField(help_text="Falso enquanto a base não for importada.")
    filtros = FiltrosTribunalSerializer(required=False)
    geral = TaxaTribunalSerializer(required=False)
    fora_da_taxa = ForaDaTaxaSerializer(many=True, required=False)
    por_vara = TaxaTribunalPorVaraSerializer(many=True, required=False)
    por_ano = TaxaTribunalPorAnoSerializer(many=True, required=False)
    validacao = ValidacaoTribunalSerializer(required=False)
    opcoes = OpcoesTribunalSerializer(required=False)
    fonte = FonteTribunalSerializer(required=False)
    populacao = serializers.CharField(required=False)
    criterio = serializers.CharField(required=False)
    piso_amostra = serializers.IntegerField(required=False)


class DecisaoTribunalSerializer(serializers.Serializer):
    numero_cnj = serializers.CharField()
    vara = serializers.CharField()
    data_sentenca = serializers.DateField(allow_null=True)
    resultado = serializers.CharField()
    grau = serializers.IntegerField(allow_null=True)
    mecanismo = serializers.CharField(help_text="Como o resultado foi lido pela regra.")
    trecho = serializers.CharField(help_text="Trecho do dispositivo, sem nome de parte.")


class JurimetriaTribunalDecisoesRespostaSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    exibidos = serializers.IntegerField(help_text="A lista é cortada em 200 itens.")
    contagem = serializers.DictField(child=serializers.IntegerField())
    decisoes = DecisaoTribunalSerializer(many=True)


class MetricasSerializer(serializers.Serializer):
    processos_ativos = serializers.IntegerField()
    novos_clientes_mes = serializers.IntegerField()
    prazos_semana = serializers.IntegerField()
    audiencias_proximas = serializers.IntegerField()


class EvolucaoMensalSerializer(serializers.Serializer):
    mes = serializers.CharField()
    ativos = serializers.IntegerField()
    novos = serializers.IntegerField()


class PrazoDiarioSerializer(serializers.Serializer):
    dia = serializers.CharField()
    qtd = serializers.IntegerField()


class DashboardRespostaSerializer(serializers.Serializer):
    metricas = MetricasSerializer()
    evolucao_processos = EvolucaoMensalSerializer(many=True)
    status_processos = NomeValorSerializer(many=True)
    prazos_semana = PrazoDiarioSerializer(many=True)
    processos_recentes = ProcessoSerializer(many=True)
    proximos_eventos = EventoAgendaSerializer(many=True)
