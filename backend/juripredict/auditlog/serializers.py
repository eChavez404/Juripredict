from rest_framework import serializers

from .models import EventoAuditoria


class EventoAuditoriaSerializer(serializers.ModelSerializer):
    ator_nome = serializers.SerializerMethodField()

    class Meta:
        model = EventoAuditoria
        fields = (
            "id",
            "ator",
            "ator_nome",
            "acao",
            "recurso_tipo",
            "recurso_id",
            "alteracoes",
            "criado_em",
        )
        read_only_fields = fields

    def get_ator_nome(self, instance):
        if not instance.ator:
            return None
        return instance.ator.first_name or instance.ator.email or instance.ator.username

