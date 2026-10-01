# Generated manually to keep the audit schema explicit and reviewable.
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organizations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EventoAuditoria",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("acao", models.CharField(max_length=100)),
                ("recurso_tipo", models.CharField(max_length=100)),
                ("recurso_id", models.CharField(max_length=64)),
                ("alteracoes", models.JSONField(blank=True, default=dict)),
                ("criado_em", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "ator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="eventos_auditoria",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "escritorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="eventos_auditoria",
                        to="organizations.escritorio",
                    ),
                ),
            ],
            options={"ordering": ("-criado_em", "-id")},
        ),
        migrations.AddIndex(
            model_name="eventoauditoria",
            index=models.Index(
                fields=["escritorio", "criado_em"], name="audit_esc_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="eventoauditoria",
            index=models.Index(
                fields=["escritorio", "recurso_tipo", "recurso_id"],
                name="audit_esc_resource_idx",
            ),
        ),
    ]

