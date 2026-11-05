from zoneinfo import available_timezones

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .emails import uma_linha
from .models import ConviteEscritorio, Escritorio, MembroEscritorio


class UsuarioMembroSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="first_name", read_only=True)

    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "nome")
        read_only_fields = fields


class EscritorioResumoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Escritorio
        fields = ("id", "nome", "fuso_horario")
        read_only_fields = fields


class EscritorioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Escritorio
        fields = (
            "id",
            "nome",
            "fuso_horario",
            "ativo",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = ("id", "ativo", "criado_em", "atualizado_em")

    def validate_nome(self, value):
        return uma_linha(value)

    def validate_fuso_horario(self, value):
        # Um fuso inválido faria os lembretes do escritório falharem em silêncio.
        if value not in available_timezones():
            raise serializers.ValidationError("Informe um fuso horário válido, como America/Sao_Paulo.")
        return value


class MembroEscritorioSerializer(serializers.ModelSerializer):
    usuario = UsuarioMembroSerializer(read_only=True)
    escritorio = EscritorioResumoSerializer(read_only=True)

    class Meta:
        model = MembroEscritorio
        fields = (
            "id",
            "escritorio",
            "usuario",
            "papel",
            "status",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = (
            "id",
            "escritorio",
            "usuario",
            "criado_em",
            "atualizado_em",
        )



class ConviteEscritorioSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConviteEscritorio
        fields = ("id", "email", "papel", "criado_em", "expira_em")
        read_only_fields = ("id", "criado_em", "expira_em")
