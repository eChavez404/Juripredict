import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0001_initial"),
        ("api", "0002_eventoagenda_alter_cliente_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="cliente",
            name="escritorio",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="clientes",
                to="organizations.escritorio",
            ),
        ),
        migrations.AddField(
            model_name="processo",
            name="escritorio",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="processos",
                to="organizations.escritorio",
            ),
        ),
        migrations.AddField(
            model_name="eventoagenda",
            name="escritorio",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="eventos_agenda",
                to="organizations.escritorio",
            ),
        ),
    ]

