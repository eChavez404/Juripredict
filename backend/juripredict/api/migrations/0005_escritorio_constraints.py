import django.db.models.deletion
from django.db import migrations, models


def validar_backfill(apps, schema_editor):
    for nome in ("Cliente", "Processo", "EventoAgenda"):
        Modelo = apps.get_model("api", nome)
        if Modelo.objects.using(schema_editor.connection.alias).filter(
            escritorio__isnull=True
        ).exists():
            raise RuntimeError(
                f"Não é possível tornar {nome}.escritorio obrigatório: existem órfãos."
            )


class Migration(migrations.Migration):
    dependencies = [("api", "0004_backfill_escritorios")]

    operations = [
        migrations.RunPython(validar_backfill, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="cliente",
            name="escritorio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="clientes",
                to="organizations.escritorio",
            ),
        ),
        migrations.AlterField(
            model_name="processo",
            name="escritorio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="processos",
                to="organizations.escritorio",
            ),
        ),
        migrations.AlterField(
            model_name="eventoagenda",
            name="escritorio",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="eventos_agenda",
                to="organizations.escritorio",
            ),
        ),
        migrations.AddConstraint(
            model_name="cliente",
            constraint=models.UniqueConstraint(
                fields=("escritorio", "cpf_cnpj_hash"),
                name="cliente_documento_unico_por_escritorio",
            ),
        ),
        migrations.AddConstraint(
            model_name="processo",
            constraint=models.UniqueConstraint(
                fields=("escritorio", "numero_cnj"),
                name="processo_cnj_unico_por_escritorio",
            ),
        ),
        migrations.AddIndex(
            model_name="processo",
            index=models.Index(
                fields=["escritorio", "status"], name="proc_esc_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="eventoagenda",
            index=models.Index(
                fields=["escritorio", "inicio"], name="evento_esc_inicio_idx"
            ),
        ),
    ]

