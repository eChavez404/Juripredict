import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .crypto_utils import decrypt_data, encrypt_data, hash_data
from .models import Cliente, EventoAgenda, Processo


def somente_digitos(value: str) -> str:
    return re.sub(r"\D", "", value)


class UsuarioSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="first_name", required=False, allow_blank=True)

    class Meta:
        model = get_user_model()
        fields = ("id", "username", "email", "nome")
        read_only_fields = ("id", "username")

    def validate_email(self, value):
        queryset = get_user_model().objects.filter(email__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Este e-mail já está em uso.")
        return value


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        login = attrs.get(self.username_field, "").strip()
        if "@" in login:
            user = get_user_model().objects.filter(email__iexact=login).first()
            if user:
                attrs[self.username_field] = user.get_username()

        data = super().validate(attrs)
        data["user"] = UsuarioSerializer(self.user).data
        return data


class AlterarSenhaSerializer(serializers.Serializer):
    senha_atual = serializers.CharField(write_only=True)
    nova_senha = serializers.CharField(write_only=True, min_length=8)

    def validate_senha_atual(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("A senha atual está incorreta.")
        return value

    def validate_nova_senha(self, value):
        validate_password(value, self.context["request"].user)
        return value


class ClienteSerializer(serializers.ModelSerializer):
    cpf_cnpj = serializers.CharField(max_length=20)
    processos_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Cliente
        fields = (
            "id",
            "nome",
            "cpf_cnpj",
            "email",
            "telefone",
            "tipo",
            "processos_count",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = ("id", "processos_count", "criado_em", "atualizado_em")

    def validate_cpf_cnpj(self, value):
        documento = somente_digitos(value)
        if len(documento) not in (11, 14):
            raise serializers.ValidationError("Informe um CPF ou CNPJ com 11 ou 14 dígitos.")

        request = self.context.get("request")
        if request and request.user.is_authenticated:
            queryset = Cliente.objects.filter(
                usuario=request.user,
                cpf_cnpj_hash=hash_data(documento),
            )
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError("Já existe um cliente com este CPF/CNPJ.")
        return documento

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["cpf_cnpj"] = decrypt_data(instance.cpf_cnpj)
        return representation

    def create(self, validated_data):
        documento = validated_data.pop("cpf_cnpj")
        return Cliente.objects.create(
            usuario=self.context["request"].user,
            cpf_cnpj=encrypt_data(documento),
            cpf_cnpj_hash=hash_data(documento),
            **validated_data,
        )

    def update(self, instance, validated_data):
        documento = validated_data.pop("cpf_cnpj", None)
        if documento is not None:
            instance.cpf_cnpj = encrypt_data(documento)
            instance.cpf_cnpj_hash = hash_data(documento)
        return super().update(instance, validated_data)


class ProcessoSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True)
    arquivo_peticao_inicial_url = serializers.SerializerMethodField()

    class Meta:
        model = Processo
        fields = (
            "id",
            "numero_cnj",
            "titulo",
            "area",
            "vara",
            "comarca",
            "cliente",
            "cliente_nome",
            "parte_contraria",
            "status",
            "resultado",
            "valor_causa",
            "data_distribuicao",
            "observacoes",
            "arquivo_peticao_inicial",
            "arquivo_peticao_inicial_url",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = (
            "id",
            "cliente_nome",
            "arquivo_peticao_inicial_url",
            "criado_em",
            "atualizado_em",
        )
        extra_kwargs = {"arquivo_peticao_inicial": {"write_only": True, "required": False}}

    def get_arquivo_peticao_inicial_url(self, instance):
        if not instance.arquivo_peticao_inicial:
            return None
        request = self.context.get("request")
        url = instance.arquivo_peticao_inicial.url
        return request.build_absolute_uri(url) if request else url

    def validate_numero_cnj(self, value):
        digits = somente_digitos(value)
        if len(digits) != 20:
            raise serializers.ValidationError("O número CNJ deve conter 20 dígitos.")
        value = (
            f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}."
            f"{digits[13]}.{digits[14:16]}.{digits[16:]}"
        )
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            queryset = Processo.objects.filter(usuario=request.user, numero_cnj=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError("Este processo já está cadastrado.")
        return value

    def validate_arquivo_peticao_inicial(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("O arquivo deve ter no máximo 10 MB.")
        extension = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if extension not in {"pdf", "doc", "docx"}:
            raise serializers.ValidationError("Envie um arquivo PDF, DOC ou DOCX.")
        return value

    def validate_cliente(self, cliente):
        if cliente.usuario_id != self.context["request"].user.id:
            raise serializers.ValidationError("Cliente inválido para este usuário.")
        return cliente

    def create(self, validated_data):
        return Processo.objects.create(usuario=self.context["request"].user, **validated_data)


class EventoAgendaSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source="processo.numero_cnj", read_only=True)
    cliente_nome = serializers.CharField(source="processo.cliente.nome", read_only=True)

    class Meta:
        model = EventoAgenda
        fields = (
            "id",
            "titulo",
            "tipo",
            "inicio",
            "fim",
            "processo",
            "processo_numero",
            "cliente_nome",
            "local",
            "descricao",
            "concluido",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = (
            "id",
            "processo_numero",
            "cliente_nome",
            "criado_em",
            "atualizado_em",
        )

    def validate_processo(self, processo):
        if processo and processo.usuario_id != self.context["request"].user.id:
            raise serializers.ValidationError("Processo inválido para este usuário.")
        return processo

    def validate(self, attrs):
        inicio = attrs.get("inicio", getattr(self.instance, "inicio", None))
        fim = attrs.get("fim", getattr(self.instance, "fim", None))
        if inicio and fim and fim < inicio:
            raise serializers.ValidationError({"fim": "O término deve ser posterior ao início."})
        return attrs

    def create(self, validated_data):
        return EventoAgenda.objects.create(
            usuario=self.context["request"].user,
            **validated_data,
        )
