from django.conf import settings
from django.db import models


class Cliente(models.Model):
    TIPO_CHOICES = (
        ("PF", "Pessoa Física"),
        ("PJ", "Pessoa Jurídica"),
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="clientes",
        null=True,
        blank=True,
    )
    escritorio = models.ForeignKey(
        "organizations.Escritorio",
        on_delete=models.PROTECT,
        related_name="clientes",
    )
    nome = models.CharField(max_length=255)
    cpf_cnpj = models.CharField(max_length=255)
    cpf_cnpj_hash = models.CharField(max_length=64, blank=True, db_index=True)
    email = models.EmailField(blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    tipo = models.CharField(max_length=2, choices=TIPO_CHOICES, default="PF")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nome",)
        constraints = [
            models.UniqueConstraint(
                fields=("escritorio", "cpf_cnpj_hash"),
                name="cliente_documento_unico_por_escritorio",
            ),
        ]

    def __str__(self):
        return self.nome


class Processo(models.Model):
    STATUS_CHOICES = (
        ("ATIVO", "Ativo"),
        ("SUSPENSO", "Suspenso"),
        ("ARQUIVADO", "Arquivado"),
    )
    AREA_CHOICES = (
        ("TRABALHISTA", "Trabalhista"),
        ("CIVEL", "Cível"),
        ("PREVIDENCIARIO", "Previdenciário"),
        ("TRIBUTARIO", "Tributário"),
        ("CRIMINAL", "Criminal"),
        ("OUTRO", "Outro"),
    )
    RESULTADO_CHOICES = (
        ("PENDENTE", "Pendente"),
        ("FAVORAVEL", "Favorável"),
        ("DESFAVORAVEL", "Desfavorável"),
        ("ACORDO", "Acordo"),
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="processos",
        null=True,
        blank=True,
    )
    escritorio = models.ForeignKey(
        "organizations.Escritorio",
        on_delete=models.PROTECT,
        related_name="processos",
    )
    numero_cnj = models.CharField(max_length=25)
    titulo = models.CharField(max_length=255, blank=True)
    area = models.CharField(max_length=20, choices=AREA_CHOICES, default="TRABALHISTA")
    vara = models.CharField(max_length=100)
    comarca = models.CharField(max_length=100)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="processos")
    parte_contraria = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ATIVO")
    resultado = models.CharField(max_length=20, choices=RESULTADO_CHOICES, default="PENDENTE")
    valor_causa = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    data_distribuicao = models.DateField(null=True, blank=True)
    observacoes = models.TextField(blank=True)
    arquivo_peticao_inicial = models.FileField(
        upload_to="processos/peticoes/", blank=True, null=True
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-atualizado_em",)
        indexes = [
            models.Index(fields=("usuario", "status")),
            models.Index(
                fields=("escritorio", "status"), name="proc_esc_status_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("escritorio", "numero_cnj"),
                name="processo_cnj_unico_por_escritorio",
            ),
        ]

    def __str__(self):
        return f"{self.numero_cnj} - {self.cliente.nome}"


class EventoAgenda(models.Model):
    TIPO_CHOICES = (
        ("AUDIENCIA", "Audiência"),
        ("PRAZO", "Prazo"),
        ("REUNIAO", "Reunião"),
        ("OUTRO", "Outro"),
    )

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="eventos_agenda",
        null=True,
        blank=True,
    )
    escritorio = models.ForeignKey(
        "organizations.Escritorio",
        on_delete=models.PROTECT,
        related_name="eventos_agenda",
    )
    processo = models.ForeignKey(
        Processo,
        on_delete=models.SET_NULL,
        related_name="eventos",
        null=True,
        blank=True,
    )
    titulo = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="PRAZO")
    inicio = models.DateTimeField()
    fim = models.DateTimeField(null=True, blank=True)
    local = models.CharField(max_length=255, blank=True)
    descricao = models.TextField(blank=True)
    concluido = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("inicio",)
        indexes = [
            models.Index(fields=("usuario", "inicio")),
            models.Index(
                fields=("escritorio", "inicio"), name="evento_esc_inicio_idx"
            ),
        ]

    def __str__(self):
        return self.titulo
