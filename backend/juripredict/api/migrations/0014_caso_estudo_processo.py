import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0013_casos_de_estudo"),
    ]

    operations = [
        migrations.AddField(
            model_name="casoestudo",
            name="processo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="casos_estudo",
                to="api.processo",
            ),
        ),
        migrations.AddField(
            model_name="mensagemcaso",
            name="documentos_lidos",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
