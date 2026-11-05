from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from accounts.throttles import ContaLoginThrottle
from accounts.tokens_api import revogar_tokens_api
from auditlog.mixins import AuditoriaCrudMixin
from auditlog.services import registrar_evento_auditoria
from config.openapi import (
    AndamentosRespostaSerializer,
    DashboardRespostaSerializer,
    DetalheSerializer,
    JurimetriaProcessosRespostaSerializer,
    JurimetriaRespostaSerializer,
    PendenciasRespostaSerializer,
    PrazoCalculoRespostaSerializer,
    SessaoSerializer,
    SincronizacaoRespostaSerializer,
)
from organizations.context import EscritorioContextMixin
from organizations.permissions import TemContextoEscritorio, exige_capability

from .andamentos import sincronizar_processo
from .documentos import anexar_documento, remover_documento
from .datajud import DatajudErro
from .jurimetria import (
    RESULTADOS_CONCLUIDOS,
    analisar,
    aplicar_filtros,
    concluidos,
    descrever_recorte,
    exportar_csv,
    filtros_da_requisicao,
    opcoes_de_filtro,
    resposta_publica,
)
from .models import Andamento, Cliente, DocumentoProcesso, EventoAgenda, Processo
from .prazos import calcular_prazo
from .serializers import (
    AlterarSenhaSerializer,
    AndamentoRecenteSerializer,
    AndamentoSerializer,
    ClienteSerializer,
    CustomTokenObtainPairSerializer,
    DocumentoProcessoSerializer,
    EventoAgendaSerializer,
    PrazoParametrosSerializer,
    ProcessoResumoSerializer,
    ProcessoSerializer,
    UsuarioSerializer,
)


FILTROS_JURIMETRIA = [
    OpenApiParameter("area", str, enum=[valor for valor, _ in Processo.AREA_CHOICES]),
    OpenApiParameter("ano", str, description="Ano de distribuição, ou sem_data."),
]

MESES = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def inicio_mes_retroativo(referencia: date, meses: int) -> date:
    indice = referencia.year * 12 + referencia.month - 1 - meses
    return date(indice // 12, indice % 12 + 1, 1)


@extend_schema_view(post=extend_schema(responses=SessaoSerializer))
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle, ContaLoginThrottle]
    throttle_scope = "login"


class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "refresh"


class UsuarioAtualAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UsuarioSerializer)
    def get(self, request):
        return Response(UsuarioSerializer(request.user, context={"request": request}).data)

    @extend_schema(request=UsuarioSerializer, responses=UsuarioSerializer)
    def patch(self, request):
        serializer = UsuarioSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class AlterarSenhaAPIView(APIView):
    permission_classes = [IsAuthenticated]
    # pede a senha: quem tem um token roubado não deve poder testar senhas aqui
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conta_sensivel"

    @extend_schema(request=AlterarSenhaSerializer, responses=DetalheSerializer)
    def post(self, request):
        serializer = AlterarSenhaSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["nova_senha"])
        request.user.save(update_fields=("password",))
        revogar_tokens_api(request.user)
        return Response({"detail": "Senha alterada com sucesso."})


@extend_schema_view(
    list=extend_schema(
        parameters=[OpenApiParameter("q", str, description="Busca por nome ou e-mail.")]
    ),
    destroy=extend_schema(responses={204: None, 409: DetalheSerializer}),
)
class ClienteViewSet(AuditoriaCrudMixin, EscritorioContextMixin, viewsets.ModelViewSet):
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated, TemContextoEscritorio]
    recurso_auditoria = "cliente"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Cliente.objects.none()
        queryset = Cliente.objects.filter(escritorio=self.get_escritorio()).annotate(
            processos_count=Count("processos", distinct=True)
        )
        termo = self.request.query_params.get("q", "").strip()
        if termo:
            queryset = queryset.filter(Q(nome__icontains=termo) | Q(email__icontains=termo))
        return queryset

    def get_permissions(self):
        permissoes = super().get_permissions()
        if self.action == "destroy":
            permissoes.append(exige_capability("clientes.excluir")())
        return permissoes

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "Este cliente possui processos e não pode ser excluído."},
                status=status.HTTP_409_CONFLICT,
            )


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Busca por CNJ, cliente ou parte contrária."),
            OpenApiParameter("status", str, enum=[valor for valor, _ in Processo.STATUS_CHOICES]),
        ]
    )
)
class ProcessoViewSet(AuditoriaCrudMixin, EscritorioContextMixin, viewsets.ModelViewSet):
    serializer_class = ProcessoSerializer
    permission_classes = [IsAuthenticated, TemContextoEscritorio]
    recurso_auditoria = "processo"
    # o DRF só aceita `throttle_scope` por action se a classe o declarar
    throttle_scope = None

    def get_permissions(self):
        permissoes = super().get_permissions()
        if self.action == "destroy":
            permissoes.append(exige_capability("processos.excluir")())
        return permissoes

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Processo.objects.none()
        queryset = Processo.objects.filter(escritorio=self.get_escritorio()).select_related(
            "cliente"
        )
        termo = self.request.query_params.get("q", "").strip()
        situacao = self.request.query_params.get("status", "").strip().upper()
        if termo:
            queryset = queryset.filter(
                Q(numero_cnj__icontains=termo)
                | Q(cliente__nome__icontains=termo)
                | Q(parte_contraria__icontains=termo)
            )
        if situacao in dict(Processo.STATUS_CHOICES):
            queryset = queryset.filter(status=situacao)
        return queryset

    def _andamentos(self, processo):
        return {
            "sincronizado_em": processo.andamentos_sincronizados_em,
            "andamentos": AndamentoSerializer(processo.andamentos.all()[:200], many=True).data,
        }

    @extend_schema(methods=["get"], responses=DocumentoProcessoSerializer(many=True))
    @extend_schema(
        methods=["post"],
        request={"multipart/form-data": DocumentoProcessoSerializer},
        responses={201: DocumentoProcessoSerializer},
    )
    @action(detail=True, methods=["get", "post"])
    def documentos(self, request, pk=None):
        processo = self.get_object()
        if request.method == "POST":
            serializer = DocumentoProcessoSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            documento = anexar_documento(
                processo=processo,
                arquivo=serializer.validated_data["arquivo"],
                usuario=request.user,
            )
            dados = DocumentoProcessoSerializer(documento, context={"request": request}).data
            return Response(dados, status=status.HTTP_201_CREATED)
        serializer = DocumentoProcessoSerializer(
            processo.documentos.select_related("enviado_por"),
            many=True,
            context={"request": request},
        )
        return Response(serializer.data)

    @extend_schema(
        parameters=[OpenApiParameter("documento_id", int, OpenApiParameter.PATH)],
        responses={204: None},
    )
    @action(detail=True, methods=["delete"], url_path=r"documentos/(?P<documento_id>\d+)")
    def excluir_documento(self, request, pk=None, documento_id=None):
        processo = self.get_object()
        documento = get_object_or_404(DocumentoProcesso, pk=documento_id, processo=processo)
        remover_documento(documento=documento, usuario=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(responses=AndamentosRespostaSerializer)
    @action(detail=True, methods=["get"])
    def andamentos(self, request, pk=None):
        return Response(self._andamentos(self.get_object()))

    @extend_schema(
        request=None,
        responses={
            200: SincronizacaoRespostaSerializer,
            400: DetalheSerializer,
            503: DetalheSerializer,
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="andamentos/sincronizar",
        throttle_classes=[ScopedRateThrottle],
        throttle_scope="andamentos",
    )
    def sincronizar_andamentos(self, request, pk=None):
        """Lê o DataJud agora. Cada leitura é uma chamada externa, por isso o limite."""
        processo = self.get_object()
        try:
            novos = sincronizar_processo(processo)
        except DatajudErro as exc:
            return Response({"detail": str(exc)}, status=exc.http_status)
        processo.refresh_from_db(fields=("andamentos_sincronizados_em",))
        return Response({**self._andamentos(processo), "novos": novos})


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("inicio", date, description="Data inicial (AAAA-MM-DD)."),
            OpenApiParameter("fim", date, description="Data final (AAAA-MM-DD)."),
        ]
    )
)
class EventoAgendaViewSet(AuditoriaCrudMixin, EscritorioContextMixin, viewsets.ModelViewSet):
    serializer_class = EventoAgendaSerializer
    permission_classes = [IsAuthenticated, TemContextoEscritorio]
    recurso_auditoria = "evento_agenda"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return EventoAgenda.objects.none()
        queryset = EventoAgenda.objects.filter(escritorio=self.get_escritorio()).select_related(
            "processo", "processo__cliente"
        )
        inicio = self._data_do_filtro("inicio")
        fim = self._data_do_filtro("fim")
        if inicio:
            queryset = queryset.filter(inicio__date__gte=inicio)
        if fim:
            queryset = queryset.filter(inicio__date__lte=fim)
        return queryset

    def _data_do_filtro(self, parametro):
        valor = self.request.query_params.get(parametro)
        if not valor:
            return None
        try:
            data = parse_date(valor)
        except ValueError:  # formato certo, data impossível (ex.: dia 31 de fevereiro)
            data = None
        if data is None:
            raise ValidationError({parametro: ["Informe uma data válida, no formato AAAA-MM-DD."]})
        return data


class DashboardAPIView(EscritorioContextMixin, APIView):
    permission_classes = [IsAuthenticated, TemContextoEscritorio]

    @extend_schema(responses=DashboardRespostaSerializer)
    def get(self, request):
        hoje = timezone.localdate()
        agora = timezone.now()
        inicio_semana = hoje - timedelta(days=hoje.weekday())
        fim_semana = inicio_semana + timedelta(days=6)
        inicio_mes = hoje.replace(day=1)

        escritorio = self.get_escritorio()
        processos = Processo.objects.filter(escritorio=escritorio).select_related("cliente")
        clientes = Cliente.objects.filter(escritorio=escritorio)
        eventos = EventoAgenda.objects.filter(escritorio=escritorio)

        status_processos = {
            item["status"]: item["total"]
            for item in processos.values("status").annotate(total=Count("id"))
        }
        eventos_semana = eventos.filter(
            inicio__date__gte=inicio_semana,
            inicio__date__lte=fim_semana,
            concluido=False,
        )

        evolucao = []
        for deslocamento in reversed(range(6)):
            mes = inicio_mes_retroativo(hoje, deslocamento)
            proximo_mes = inicio_mes_retroativo(hoje, deslocamento - 1)
            evolucao.append(
                {
                    "mes": MESES[mes.month - 1],
                    "ativos": processos.filter(criado_em__date__lt=proximo_mes)
                    .exclude(status="ARQUIVADO")
                    .count(),
                    "novos": processos.filter(
                        criado_em__date__gte=mes,
                        criado_em__date__lt=proximo_mes,
                    ).count(),
                }
            )

        prazos_por_dia = {dia: 0 for dia in DIAS[:5]}
        for evento in eventos_semana.filter(tipo="PRAZO"):
            dia = DIAS[timezone.localtime(evento.inicio).weekday()]
            if dia in prazos_por_dia:
                prazos_por_dia[dia] += 1

        recentes = ProcessoSerializer(
            processos.order_by("-atualizado_em")[:5],
            many=True,
            context={"request": request},
        ).data
        proximos_eventos = EventoAgendaSerializer(
            eventos.filter(inicio__gte=agora, concluido=False).order_by("inicio")[:5],
            many=True,
            context={"request": request},
        ).data

        return Response(
            {
                "metricas": {
                    "processos_ativos": status_processos.get("ATIVO", 0),
                    "novos_clientes_mes": clientes.filter(criado_em__date__gte=inicio_mes).count(),
                    "prazos_semana": eventos_semana.filter(tipo="PRAZO").count(),
                    "audiencias_proximas": eventos.filter(
                        tipo="AUDIENCIA", inicio__gte=agora, concluido=False
                    ).count(),
                },
                "evolucao_processos": evolucao,
                "status_processos": [
                    {"name": "Ativos", "value": status_processos.get("ATIVO", 0)},
                    {"name": "Suspensos", "value": status_processos.get("SUSPENSO", 0)},
                    {"name": "Arquivados", "value": status_processos.get("ARQUIVADO", 0)},
                ],
                "prazos_semana": [
                    {"dia": dia, "qtd": quantidade}
                    for dia, quantidade in prazos_por_dia.items()
                ],
                "processos_recentes": recentes,
                "proximos_eventos": proximos_eventos,
            }
        )


class JurimetriaAPIView(EscritorioContextMixin, APIView):
    permission_classes = [IsAuthenticated, TemContextoEscritorio, exige_capability("jurimetria.ler")]

    @extend_schema(parameters=FILTROS_JURIMETRIA, responses=JurimetriaRespostaSerializer)
    def get(self, request):
        piso = settings.JURIMETRIA_PISO_AMOSTRA
        todos = Processo.objects.filter(escritorio=self.get_escritorio())
        filtros = filtros_da_requisicao(request.query_params)
        filtros.pop("resultado", None)  # a taxa é sobre todos os resultados do recorte
        filtros.pop("vara", None)
        processos = aplicar_filtros(todos, filtros)
        analise = analisar(processos, piso=piso)
        geral = analise["geral"]
        contagem = analise["contagem_geral"]
        return Response(
            {
                "total_analisados": geral["total"],
                "taxa_favoravel": geral["favoravel"],
                "intervalo_favoravel": geral["intervalo_favoravel"],
                "amostra_suficiente": geral["suficiente"],
                "piso_amostra": piso,
                "processos_ativos": processos.filter(status="ATIVO").count(),
                **resposta_publica(analise),
                "resultados": [
                    {"name": "Favoráveis", "value": contagem.get("FAVORAVEL", 0)},
                    {"name": "Acordos", "value": contagem.get("ACORDO", 0)},
                    {"name": "Desfavoráveis", "value": contagem.get("DESFAVORAVEL", 0)},
                ],
                "filtros": {
                    "area": filtros.get("area"),
                    "ano": str(filtros["ano"]) if "ano" in filtros else None,
                },
                "opcoes": opcoes_de_filtro(todos),
                "insight": self._insight(geral["total"], geral, analise["por_vara"], piso),
            }
        )

    @staticmethod
    def _insight(total, geral, por_vara, piso):
        if not total:
            return (
                "Cadastre o resultado dos processos encerrados para gerar indicadores "
                "jurimétricos baseados na sua própria carteira."
            )
        if not geral["suficiente"]:
            return (
                f"Com {total} processos concluídos, ainda não há amostra para taxas "
                f"confiáveis: o mínimo é {piso}. Continue cadastrando os resultados "
                "dos processos encerrados."
            )
        intervalo = geral["intervalo_favoravel"]
        suficientes = [item for item in por_vara if item["suficiente"]]
        destaque = (
            f"{suficientes[0]['vara']} concentra o maior volume analisado."
            if suficientes
            else "Nenhuma vara tem amostra suficiente para taxa própria."
        )
        return (
            f"Com base em {total} processos concluídos, {geral['favoravel']}% tiveram "
            f"resultado favorável ou acordo (intervalo de confiança de 95%: "
            f"{intervalo['min']}% a {intervalo['max']}%). {destaque}"
        )


class JurimetriaProcessosAPIView(EscritorioContextMixin, APIView):
    """Os processos por trás de um número: nenhuma taxa fica sem como ser conferida."""

    permission_classes = [IsAuthenticated, TemContextoEscritorio, exige_capability("jurimetria.ler")]
    LIMITE = 200

    @extend_schema(
        parameters=FILTROS_JURIMETRIA
        + [
            OpenApiParameter("vara", str, description="Vara exatamente como cadastrada."),
            OpenApiParameter("resultado", str, enum=list(RESULTADOS_CONCLUIDOS)),
        ],
        responses=JurimetriaProcessosRespostaSerializer,
    )
    def get(self, request):
        processos = aplicar_filtros(
            concluidos(Processo.objects.filter(escritorio=self.get_escritorio())),
            filtros_da_requisicao(request.query_params),
        ).select_related("cliente").order_by("vara", "-data_distribuicao", "-id")
        total = processos.count()
        itens = ProcessoResumoSerializer(processos[: self.LIMITE], many=True).data
        return Response({"total": total, "exibidos": len(itens), "processos": itens})


class JurimetriaExportarAPIView(EscritorioContextMixin, APIView):
    permission_classes = [IsAuthenticated, TemContextoEscritorio, exige_capability("jurimetria.ler")]

    @extend_schema(
        parameters=FILTROS_JURIMETRIA,
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def get(self, request):
        filtros = filtros_da_requisicao(request.query_params)
        filtros.pop("resultado", None)
        filtros.pop("vara", None)
        escritorio = self.get_escritorio()
        analise = analisar(
            aplicar_filtros(Processo.objects.filter(escritorio=escritorio), filtros),
            piso=settings.JURIMETRIA_PISO_AMOSTRA,
        )
        recorte = descrever_recorte(filtros)
        # os dados saem do sistema: quem administra o escritório precisa saber
        registrar_evento_auditoria(
            escritorio=escritorio,
            ator=request.user,
            acao="jurimetria.exportada",
            recurso_tipo="jurimetria",
            recurso_id="carteira",
            alteracoes={"recorte": recorte},
        )
        resposta = HttpResponse(
            exportar_csv(analise, descricao_recorte=recorte), content_type="text/csv; charset=utf-8"
        )
        resposta["Content-Disposition"] = 'attachment; filename="jurimetria-carteira.csv"'
        return resposta


class PrazoCalculoAPIView(APIView):
    """Só calcula: não lê nem grava dado de escritório. Quem grava é a criação do compromisso."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[PrazoParametrosSerializer], responses=PrazoCalculoRespostaSerializer)
    def get(self, request):
        parametros = PrazoParametrosSerializer(data=request.query_params)
        parametros.is_valid(raise_exception=True)
        return Response(calcular_prazo(**parametros.validated_data))


class PendenciasAPIView(EscritorioContextMixin, APIView):
    """O que precisa de atenção agora, calculado na hora: não há estado a manter em dia."""

    permission_classes = [IsAuthenticated, TemContextoEscritorio]
    LIMITE = 20
    DIAS_A_FRENTE = 7
    DIAS_DE_ANDAMENTOS = 7

    @extend_schema(responses=PendenciasRespostaSerializer)
    def get(self, request):
        escritorio = self.get_escritorio()
        hoje = timezone.localdate()
        eventos = (
            EventoAgenda.objects.filter(
                escritorio=escritorio, concluido=False, tipo__in=("PRAZO", "AUDIENCIA")
            )
            .select_related("processo", "processo__cliente")
            .order_by("inicio")
        )
        # Comparar por dia: prazo que vence hoje ainda pode ser cumprido até o fim do dia.
        vencidos = eventos.filter(tipo="PRAZO", inicio__date__lt=hoje)
        proximos = eventos.filter(
            inicio__date__gte=hoje, inicio__date__lte=hoje + timedelta(days=self.DIAS_A_FRENTE)
        )
        andamentos = (
            Andamento.objects.filter(
                processo__escritorio=escritorio,
                data_hora__gte=timezone.now() - timedelta(days=self.DIAS_DE_ANDAMENTOS),
            )
            .select_related("processo")
            .order_by("-data_hora", "-id")
        )
        contexto = {"request": request}
        total_vencidos = vencidos.count()
        return Response(
            {
                "urgentes": total_vencidos
                + proximos.filter(inicio__date__lte=hoje + timedelta(days=1)).count(),
                "total_vencidos": total_vencidos,
                "total_proximos": proximos.count(),
                "vencidos": EventoAgendaSerializer(
                    vencidos[: self.LIMITE], many=True, context=contexto
                ).data,
                "proximos": EventoAgendaSerializer(
                    proximos[: self.LIMITE], many=True, context=contexto
                ).data,
                "andamentos_recentes": AndamentoRecenteSerializer(
                    andamentos[: self.LIMITE], many=True
                ).data,
            }
        )
