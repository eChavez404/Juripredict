import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.authentication import e_token_api
from accounts.models import EmailVerificado
from accounts.services import registrar_troca_de_email
from organizations.capabilities import capabilities_do_membro, request_tem_capability
from organizations.context import contexto_escritorio_da_request
from organizations.selectors import memberships_do_usuario, resolver_membership
from organizations.serializers import EscritorioResumoSerializer, MembroEscritorioSerializer

from .crypto_utils import decrypt_data, encrypt_data, hash_data
from .models import (
    Andamento,
    Cliente,
    DocumentoProcesso,
    EventoAgenda,
    Processo,
    apagar_arquivo_depois_do_commit,
)
from .prazos import FUNDAMENTOS, INTIMACAO, PUBLICACAO_DIARIO
from .validators import validar_documento, validar_peticao_inicial


def somente_digitos(value: str) -> str:
    return re.sub(r"\D", "", value)


def mascarar_documento(documento: str) -> str:
    """Esconde todos os dígitos menos os dois últimos, mantendo a pontuação."""
    return re.sub(r"\d", "*", documento[:-2]) + documento[-2:]


class UsuarioSerializer(serializers.ModelSerializer):
    nome = serializers.CharField(source="first_name", required=False, allow_blank=True)
    memberships = serializers.SerializerMethodField()
    escritorio_ativo = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    email_verificado = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = (
            "id",
            "username",
            "email",
            "nome",
            "memberships",
            "escritorio_ativo",
            "capabilities",
            "email_verificado",
        )
        read_only_fields = (
            "id",
            "username",
            "memberships",
            "escritorio_ativo",
            "capabilities",
            "email_verificado",
        )

    def get_email_verificado(self, usuario) -> bool:
        return EmailVerificado.objects.filter(usuario=usuario).exists()

    def _membro_ativo(self, usuario):
        request = self.context.get("request")
        if request:
            return contexto_escritorio_da_request(request, obrigatorio=False)
        return resolver_membership(usuario, obrigatorio=False)

    @extend_schema_field(MembroEscritorioSerializer(many=True))
    def get_memberships(self, usuario):
        memberships = memberships_do_usuario(usuario, incluir_suspensos=True)
        return MembroEscritorioSerializer(memberships, many=True).data

    @extend_schema_field(EscritorioResumoSerializer(allow_null=True))
    def get_escritorio_ativo(self, usuario):
        membro = self._membro_ativo(usuario)
        if not membro:
            return None
        return {
            "id": str(membro.escritorio_id),
            "nome": membro.escritorio.nome,
            "fuso_horario": membro.escritorio.fuso_horario,
        }

    def get_capabilities(self, usuario) -> list[str]:
        return capabilities_do_membro(self._membro_ativo(usuario))

    def validate_email(self, value):
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError("Informe um e-mail.")
        # o username também conta: é o e-mail com que a conta foi criada, e segue valendo no login
        queryset = get_user_model().objects.filter(Q(email__iexact=value) | Q(username__iexact=value))
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("Este e-mail já está em uso.")
        return value

    def update(self, instance, validated_data):
        email_anterior = instance.email
        usuario = super().update(instance, validated_data)
        if usuario.email.lower() != email_anterior.lower():
            registrar_troca_de_email(usuario)
        return usuario


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
            "escritorio",
            "nome",
            "cpf_cnpj",
            "email",
            "telefone",
            "tipo",
            "processos_count",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = (
            "id",
            "escritorio",
            "processos_count",
            "criado_em",
            "atualizado_em",
        )
        validators = []

    def validate_cpf_cnpj(self, value):
        if self.instance and not self._ve_documento():
            # quem só vê o documento mascarado não o altera: devolve o que já está gravado
            return decrypt_data(self.instance.cpf_cnpj)
        documento = somente_digitos(value)
        if len(documento) not in (11, 14):
            raise serializers.ValidationError("Informe um CPF ou CNPJ com 11 ou 14 dígitos.")

        request = self.context.get("request")
        if request and request.user.is_authenticated:
            escritorio = contexto_escritorio_da_request(request).escritorio
            queryset = Cliente.objects.filter(
                escritorio=escritorio,
                cpf_cnpj_hash=hash_data(documento),
            )
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError("Já existe um cliente com este CPF/CNPJ.")
        return documento

    def _ve_documento(self):
        request = self.context.get("request")
        # sem request (uso interno) não há papel a respeitar
        return request is None or request_tem_capability(request, "clientes.documento.ler")

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        documento = decrypt_data(instance.cpf_cnpj)
        representation["cpf_cnpj"] = documento if self._ve_documento() else mascarar_documento(documento)
        return representation

    def create(self, validated_data):
        documento = validated_data.pop("cpf_cnpj")
        return Cliente.objects.create(
            usuario=self.context["request"].user,
            escritorio=contexto_escritorio_da_request(
                self.context["request"]
            ).escritorio,
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


class ProcessoResumoSerializer(serializers.ModelSerializer):
    """Só o que identifica o caso na lista que sustenta uma taxa; sem valor da causa."""

    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True)

    class Meta:
        model = Processo
        fields = (
            "id",
            "numero_cnj",
            "titulo",
            "vara",
            "comarca",
            "area",
            "resultado",
            "status",
            "data_distribuicao",
            "cliente_nome",
        )
        read_only_fields = fields


class PrazoParametrosSerializer(serializers.Serializer):
    data_base = serializers.DateField(
        help_text="Data da ciência, ou da disponibilização no diário eletrônico."
    )
    dias = serializers.IntegerField(min_value=1, max_value=365)
    tipo = serializers.ChoiceField(
        choices=(
            (INTIMACAO, "Ciência direta do ato"),
            (PUBLICACAO_DIARIO, "Disponibilização no diário eletrônico"),
        ),
        default=INTIMACAO,
    )
    area = serializers.ChoiceField(choices=Processo.AREA_CHOICES, default="TRABALHISTA")
    suspensoes = serializers.ListField(
        child=serializers.DateField(),
        required=False,
        max_length=120,
        help_text="Dias sem expediente conferidos no calendário do tribunal.",
    )

    def validate_data_base(self, value):
        if not 2000 <= value.year <= 2100:
            raise serializers.ValidationError("Informe uma data entre 2000 e 2100.")
        return value

    def validate_area(self, value):
        if value not in FUNDAMENTOS:
            raise serializers.ValidationError(
                "Esta área tem contagem própria e não é calculada aqui. "
                "Disponível para as áreas trabalhista e cível."
            )
        return value


class AndamentoRecenteSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source="processo.numero_cnj", read_only=True)

    class Meta:
        model = Andamento
        fields = ("id", "processo", "processo_numero", "data_hora", "nome")
        read_only_fields = fields


class AndamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Andamento
        fields = ("id", "data_hora", "codigo", "nome", "complemento")
        read_only_fields = fields


class DocumentoProcessoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    enviado_por_nome = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoProcesso
        fields = ("id", "arquivo", "nome", "tamanho", "url", "enviado_por_nome", "criado_em")
        read_only_fields = ("id", "nome", "tamanho", "url", "enviado_por_nome", "criado_em")
        extra_kwargs = {"arquivo": {"write_only": True}}

    def validate_arquivo(self, value):
        return validar_documento(value)

    def get_url(self, instance) -> str | None:
        request = self.context.get("request")
        if request and e_token_api(request.auth):
            return None
        url = instance.arquivo.url
        return request.build_absolute_uri(url) if request else url

    def get_enviado_por_nome(self, instance) -> str | None:
        usuario = instance.enviado_por
        return (usuario.first_name or usuario.email) if usuario else None


class ProcessoSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source="cliente.nome", read_only=True)
    arquivo_peticao_inicial_url = serializers.SerializerMethodField()

    class Meta:
        model = Processo
        fields = (
            "id",
            "escritorio",
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
            "andamentos_sincronizados_em",
            "arquivo_peticao_inicial",
            "arquivo_peticao_inicial_url",
            "andamentos_sincronizados_em",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = (
            "id",
            "escritorio",
            "cliente_nome",
            "arquivo_peticao_inicial_url",
            "criado_em",
            "atualizado_em",
        )
        extra_kwargs = {"arquivo_peticao_inicial": {"write_only": True, "required": False}}
        validators = []

    def get_arquivo_peticao_inicial_url(self, instance) -> str | None:
        request = self.context.get("request")
        # Link assinado abre o arquivo sem login: não vai para quem usa token de agente.
        if not instance.arquivo_peticao_inicial or (request and e_token_api(request.auth)):
            return None
        url = instance.arquivo_peticao_inicial.url
        return request.build_absolute_uri(url) if request else url

    def _ve_valores(self):
        request = self.context.get("request")
        return request is None or request_tem_capability(request, "processos.valores.ler")

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if not self._ve_valores():
            representation["valor_causa"] = None
        return representation

    def validate(self, attrs):
        # quem não vê o valor da causa também não o grava: senão apagaria o valor ao salvar
        # o formulário (que o recebe nulo) ou poderia sobrescrevê-lo às cegas
        if not self._ve_valores():
            attrs.pop("valor_causa", None)
        return attrs

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
            escritorio = contexto_escritorio_da_request(request).escritorio
            queryset = Processo.objects.filter(escritorio=escritorio, numero_cnj=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError("Este processo já está cadastrado.")
        return value

    def validate_arquivo_peticao_inicial(self, value):
        return validar_peticao_inicial(value)

    def validate_cliente(self, cliente):
        escritorio = contexto_escritorio_da_request(
            self.context["request"]
        ).escritorio
        if cliente.escritorio_id != escritorio.id:
            raise serializers.ValidationError("Cliente inválido para este escritório.")
        return cliente

    def create(self, validated_data):
        request = self.context["request"]
        return Processo.objects.create(
            usuario=request.user,
            escritorio=contexto_escritorio_da_request(request).escritorio,
            **validated_data,
        )

    def update(self, instance, validated_data):
        anterior = instance.arquivo_peticao_inicial
        processo = super().update(instance, validated_data)
        if "arquivo_peticao_inicial" in validated_data:
            apagar_arquivo_depois_do_commit(anterior)
        return processo


class EventoAgendaSerializer(serializers.ModelSerializer):
    processo_numero = serializers.CharField(source="processo.numero_cnj", read_only=True)
    cliente_nome = serializers.CharField(source="processo.cliente.nome", read_only=True)

    class Meta:
        model = EventoAgenda
        fields = (
            "id",
            "escritorio",
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
            "escritorio",
            "processo_numero",
            "cliente_nome",
            "criado_em",
            "atualizado_em",
        )

    def validate_processo(self, processo):
        escritorio = contexto_escritorio_da_request(
            self.context["request"]
        ).escritorio
        if processo and processo.escritorio_id != escritorio.id:
            raise serializers.ValidationError("Processo inválido para este escritório.")
        return processo

    def validate(self, attrs):
        inicio = attrs.get("inicio", getattr(self.instance, "inicio", None))
        fim = attrs.get("fim", getattr(self.instance, "fim", None))
        if inicio and fim and fim < inicio:
            raise serializers.ValidationError({"fim": "O término deve ser posterior ao início."})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return EventoAgenda.objects.create(
            usuario=request.user,
            escritorio=contexto_escritorio_da_request(request).escritorio,
            **validated_data,
        )

    def update(self, instance, validated_data):
        # O aviso enviado era sobre a data antiga: sem isto, o prazo remarcado não teria lembrete.
        if validated_data.get("inicio", instance.inicio) != instance.inicio:
            instance.lembrete_enviado_em = None
        return super().update(instance, validated_data)
