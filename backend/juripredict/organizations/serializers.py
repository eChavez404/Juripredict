from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Escritorio, MembroEscritorio


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

