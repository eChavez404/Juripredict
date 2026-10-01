import uuid

from django.conf import settings
from django.db import models


class Escritorio(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=255)
    fuso_horario = models.CharField(max_length=64, default="America/Sao_Paulo")
    ativo = models.BooleanField(default=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="escritorios_criados",
        null=True,
        blank=True,
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nome",)

    def __str__(self):
        return self.nome


class MembroEscritorio(models.Model):
    class Papel(models.TextChoices):
        OWNER = "OWNER", "Proprietário"
        ADMIN = "ADMIN", "Administrador"
        ADVOGADO = "ADVOGADO", "Advogado"
        ESTAGIARIO = "ESTAGIARIO", "Estagiário"

    class Status(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        SUSPENSO = "SUSPENSO", "Suspenso"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    escritorio = models.ForeignKey(
        Escritorio,
        on_delete=models.CASCADE,
        related_name="membros",
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="memberships_escritorio",
    )
    papel = models.CharField(max_length=16, choices=Papel.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ATIVO)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("usuario__first_name", "usuario__email", "usuario__username")
        constraints = [
            models.UniqueConstraint(
                fields=("escritorio", "usuario"),
                name="membro_unico_por_escritorio",
            )
        ]
        indexes = [
            models.Index(
                fields=("usuario", "status"), name="membro_user_status_idx"
            )
        ]

    def __str__(self):
        return f"{self.usuario} em {self.escritorio} ({self.papel})"

