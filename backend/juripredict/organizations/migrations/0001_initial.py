# Generated manually to keep the tenancy rollout explicit and reviewable.
import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Escritorio",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("nome", models.CharField(max_length=255)),
                (
                    "fuso_horario",
                    models.CharField(default="America/Sao_Paulo", max_length=64),
                ),
                ("ativo", models.BooleanField(default=True)),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "criado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="escritorios_criados",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("nome",)},
        ),
        migrations.CreateModel(
            name="MembroEscritorio",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                (
                    "papel",
                    models.CharField(
                        choices=[
                            ("OWNER", "Proprietário"),
                            ("ADMIN", "Administrador"),
                            ("ADVOGADO", "Advogado"),
                            ("ESTAGIARIO", "Estagiário"),
                        ],
                        max_length=16,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("ATIVO", "Ativo"), ("SUSPENSO", "Suspenso")],
                        default="ATIVO",
                        max_length=16,
                    ),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("atualizado_em", models.DateTimeField(auto_now=True)),
                (
                    "escritorio",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="membros",
                        to="organizations.escritorio",
                    ),
                ),
                (
                    "usuario",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="memberships_escritorio",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": (
                    "usuario__first_name",
                    "usuario__email",
                    "usuario__username",
                )
            },
        ),
        migrations.AddConstraint(
            model_name="membroescritorio",
            constraint=models.UniqueConstraint(
                fields=("escritorio", "usuario"),
                name="membro_unico_por_escritorio",
            ),
        ),
        migrations.AddIndex(
            model_name="membroescritorio",
            index=models.Index(fields=["usuario", "status"], name="membro_user_status_idx"),
        ),
    ]

