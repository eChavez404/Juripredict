from django.db import migrations
from django.db.models import F


def criar_escritorios_e_vinculos(apps, schema_editor):
    Usuario = apps.get_model("auth", "User")
    Escritorio = apps.get_model("organizations", "Escritorio")
    MembroEscritorio = apps.get_model("organizations", "MembroEscritorio")
    Cliente = apps.get_model("api", "Cliente")
    Processo = apps.get_model("api", "Processo")
    EventoAgenda = apps.get_model("api", "EventoAgenda")
    alias = schema_editor.connection.alias

    orfaos = {
        "clientes": Cliente.objects.using(alias).filter(usuario__isnull=True).count(),
        "processos": Processo.objects.using(alias).filter(usuario__isnull=True).count(),
        "eventos": EventoAgenda.objects.using(alias).filter(usuario__isnull=True).count(),
    }
    if any(orfaos.values()):
        raise RuntimeError(
            "Migração de escritórios abortada: existem registros sem usuário: "
            f"{orfaos}. Corrija os proprietários antes de continuar."
        )

    processos_inconsistentes = (
        Processo.objects.using(alias)
        .exclude(usuario_id=F("cliente__usuario_id"))
        .count()
    )
    eventos_inconsistentes = (
        EventoAgenda.objects.using(alias)
        .filter(processo__isnull=False)
        .exclude(usuario_id=F("processo__usuario_id"))
        .count()
    )
    if processos_inconsistentes or eventos_inconsistentes:
        raise RuntimeError(
            "Migração de escritórios abortada: há relações com proprietários divergentes "
            f"(processos={processos_inconsistentes}, eventos={eventos_inconsistentes})."
        )

    escritorios_por_usuario = {}
    for usuario in Usuario.objects.using(alias).all().iterator():
        identificacao = usuario.first_name or usuario.email or usuario.username
        escritorio = Escritorio.objects.using(alias).create(
            nome=f"Escritório de {identificacao}",
            criado_por_id=usuario.pk,
        )
        MembroEscritorio.objects.using(alias).create(
            escritorio_id=escritorio.pk,
            usuario_id=usuario.pk,
            papel="OWNER",
            status="ATIVO",
        )
        escritorios_por_usuario[usuario.pk] = escritorio.pk

    for usuario_id, escritorio_id in escritorios_por_usuario.items():
        Cliente.objects.using(alias).filter(usuario_id=usuario_id).update(
            escritorio_id=escritorio_id
        )
        Processo.objects.using(alias).filter(usuario_id=usuario_id).update(
            escritorio_id=escritorio_id
        )
        EventoAgenda.objects.using(alias).filter(usuario_id=usuario_id).update(
            escritorio_id=escritorio_id
        )

    restantes = {
        "clientes": Cliente.objects.using(alias).filter(escritorio__isnull=True).count(),
        "processos": Processo.objects.using(alias).filter(escritorio__isnull=True).count(),
        "eventos": EventoAgenda.objects.using(alias).filter(escritorio__isnull=True).count(),
    }
    if any(restantes.values()):
        raise RuntimeError(
            "Migração de escritórios abortada: o backfill deixou registros órfãos: "
            f"{restantes}."
        )


class Migration(migrations.Migration):
    dependencies = [("api", "0003_add_escritorio_nullable")]

    operations = [
        migrations.RunPython(criar_escritorios_e_vinculos, migrations.RunPython.noop),
    ]

