import uuid

from django.conf import settings
from django.db import models

from organizations.models import Escritorio


class EventoAuditoria(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    escritorio = models.ForeignKey(
        Escritorio,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
    )
    ator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="eventos_auditoria",
        null=True,
        blank=True,
    )
    acao = models.CharField(max_length=100)
    recurso_tipo = models.CharField(max_length=100)
    recurso_id = models.CharField(max_length=64)
    alteracoes = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-criado_em", "-id")
        indexes = [
            models.Index(
                fields=("escritorio", "criado_em"), name="audit_esc_created_idx"
            ),
            models.Index(
                fields=("escritorio", "recurso_tipo", "recurso_id"),
                name="audit_esc_resource_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Eventos de auditoria são imutáveis.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Eventos de auditoria não podem ser excluídos.")

    def __str__(self):
        return f"{self.acao} - {self.recurso_tipo}:{self.recurso_id}"

