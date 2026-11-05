from rest_framework import serializers

from organizations.emails import uma_linha

from .models import TokenApi


class RegistroSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=150)
    # 150 é o limite do username, que recebe o e-mail
    email = serializers.EmailField(max_length=150)
    senha = serializers.CharField(write_only=True, min_length=8, max_length=128)
    escritorio_nome = serializers.CharField(max_length=255)
    aceite_termos = serializers.BooleanField()

    def validate_escritorio_nome(self, value):
        return uma_linha(value)

    def validate_aceite_termos(self, value):
        if not value:
            raise serializers.ValidationError(
                "É necessário aceitar os Termos de Uso e a Política de Privacidade."
            )
        return value


class AceitarConviteSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)
    senha = serializers.CharField(write_only=True, max_length=128)
    nome = serializers.CharField(max_length=150, required=False, allow_blank=True)
    aceite_termos = serializers.BooleanField(required=False, default=False)


class SolicitarResetSenhaSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ConfirmarResetSenhaSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    nova_senha = serializers.CharField(write_only=True, min_length=8, max_length=128)


class ExcluirContaSerializer(serializers.Serializer):
    senha = serializers.CharField(write_only=True, max_length=128)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(max_length=2048)


class ConfirmarEmailSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)


class CriarTokenApiSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=80)
    senha = serializers.CharField(write_only=True, max_length=128)
    validade_dias = serializers.IntegerField(required=False, min_value=1, max_value=365)


class TokenApiSerializer(serializers.ModelSerializer):
    ativo = serializers.BooleanField(read_only=True)

    class Meta:
        model = TokenApi
        fields = ("id", "nome", "prefixo", "criado_em", "expira_em", "ultimo_uso_em", "revogado_em", "ativo")
        read_only_fields = fields
