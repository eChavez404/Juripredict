from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count, ProtectedError, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from auditlog.mixins import AuditoriaCrudMixin
from organizations.context import EscritorioContextMixin
from organizations.permissions import TemContextoEscritorio

from .models import Cliente, EventoAgenda, Processo
from .serializers import (
    AlterarSenhaSerializer,
    ClienteSerializer,
    CustomTokenObtainPairSerializer,
    EventoAgendaSerializer,
    ProcessoSerializer,
    UsuarioSerializer,
)


MESES = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")
DIAS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")


def inicio_mes_retroativo(referencia: date, meses: int) -> date:
    indice = referencia.year * 12 + referencia.month - 1 - meses
    return date(indice // 12, indice % 12 + 1, 1)


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]


class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]


class UsuarioAtualAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UsuarioSerializer(request.user, context={"request": request}).data)

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

    def post(self, request):
        serializer = AlterarSenhaSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["nova_senha"])
        request.user.save(update_fields=("password",))
        return Response({"detail": "Senha alterada com sucesso."})


class ClienteViewSet(AuditoriaCrudMixin, EscritorioContextMixin, viewsets.ModelViewSet):
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated, TemContextoEscritorio]
    recurso_auditoria = "cliente"

    def get_queryset(self):
        queryset = Cliente.objects.filter(escritorio=self.get_escritorio()).annotate(
            processos_count=Count("processos", distinct=True)
        )
        termo = self.request.query_params.get("q", "").strip()
        if termo:
            queryset = queryset.filter(Q(nome__icontains=termo) | Q(email__icontains=termo))
        return queryset

    def destroy(self, request, *args, **kwargs):
        try:
            return super().destroy(request, *args, **kwargs)
        except ProtectedError:
            return Response(
                {"detail": "Este cliente possui processos e não pode ser excluído."},
                status=status.HTTP_409_CONFLICT,
            )


class ProcessoViewSet(AuditoriaCrudMixin, EscritorioContextMixin, viewsets.ModelViewSet):
    serializer_class = ProcessoSerializer
    permission_classes = [IsAuthenticated, TemContextoEscritorio]
    recurso_auditoria = "processo"

    def get_queryset(self):
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


class EventoAgendaViewSet(AuditoriaCrudMixin, EscritorioContextMixin, viewsets.ModelViewSet):
    serializer_class = EventoAgendaSerializer
    permission_classes = [IsAuthenticated, TemContextoEscritorio]
    recurso_auditoria = "evento_agenda"

    def get_queryset(self):
        queryset = EventoAgenda.objects.filter(escritorio=self.get_escritorio()).select_related(
            "processo", "processo__cliente"
        )
        inicio = self.request.query_params.get("inicio")
        fim = self.request.query_params.get("fim")
        if inicio:
            queryset = queryset.filter(inicio__date__gte=inicio)
        if fim:
            queryset = queryset.filter(inicio__date__lte=fim)
        return queryset


class DashboardAPIView(EscritorioContextMixin, APIView):
    permission_classes = [IsAuthenticated, TemContextoEscritorio]

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
    permission_classes = [IsAuthenticated, TemContextoEscritorio]

    def get(self, request):
        processos = Processo.objects.filter(escritorio=self.get_escritorio())
        analisados = processos.exclude(resultado="PENDENTE")
        total = analisados.count()
        favoraveis = analisados.filter(resultado__in=("FAVORAVEL", "ACORDO")).count()
        taxa_favoravel = round((favoraveis / total) * 100) if total else 0

        dados_varas = defaultdict(lambda: {"favoravel": 0, "desfavoravel": 0})
        for processo in analisados.only("vara", "resultado"):
            chave = processo.vara
            if processo.resultado in ("FAVORAVEL", "ACORDO"):
                dados_varas[chave]["favoravel"] += 1
            else:
                dados_varas[chave]["desfavoravel"] += 1

        por_vara = []
        for vara, contagem in dados_varas.items():
            quantidade = contagem["favoravel"] + contagem["desfavoravel"]
            por_vara.append(
                {
                    "vara": vara,
                    "favoravel": round(contagem["favoravel"] / quantidade * 100),
                    "desfavoravel": round(contagem["desfavoravel"] / quantidade * 100),
                    "total": quantidade,
                }
            )
        por_vara.sort(key=lambda item: (-item["total"], item["vara"]))

        resultados = {
            item["resultado"]: item["total"]
            for item in analisados.values("resultado").annotate(total=Count("id"))
        }
        distribuicao = [
            {"name": "Favoráveis", "value": resultados.get("FAVORAVEL", 0)},
            {"name": "Acordos", "value": resultados.get("ACORDO", 0)},
            {"name": "Desfavoráveis", "value": resultados.get("DESFAVORAVEL", 0)},
        ]

        if total:
            destaque = por_vara[0]["vara"] if por_vara else "a carteira atual"
            insight = (
                f"Com base em {total} processos concluídos, a carteira registra "
                f"{taxa_favoravel}% de resultados favoráveis ou acordos. "
                f"{destaque} concentra o maior volume analisado."
            )
        else:
            insight = (
                "Cadastre o resultado dos processos encerrados para gerar indicadores "
                "jurimétricos baseados na sua própria carteira."
            )

        return Response(
            {
                "total_analisados": total,
                "taxa_favoravel": taxa_favoravel,
                "processos_ativos": processos.filter(status="ATIVO").count(),
                "por_vara": por_vara[:8],
                "resultados": distribuicao,
                "insight": insight,
            }
        )
