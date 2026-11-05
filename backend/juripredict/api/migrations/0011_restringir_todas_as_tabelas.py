from django.db import migrations


def restringir_tabelas_do_django(apps, schema_editor):
    """Repete a restrição da 0007 em todas as tabelas do Django, inclusive as posteriores.

    A lista fixa da 0007 não alcança as tabelas criadas depois dela, e a ordem das
    migrações em banco novo pode criar algumas antes (accounts_tokenapi, por exemplo),
    fora do alcance do ALTER DEFAULT PRIVILEGES. Tabelas alheias ao Django não mudam.
    """
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
        )
        if {row[0] for row in cursor.fetchall()} != {"anon", "authenticated"}:
            return

        tabelas = connection.introspection.django_table_names(
            only_existing=True, include_views=False
        )
        quote = connection.ops.quote_name
        for tabela in [*tabelas, "django_migrations"]:
            cursor.execute(
                f"REVOKE ALL PRIVILEGES ON TABLE {quote(tabela)} FROM anon, authenticated"
            )
            cursor.execute(f"ALTER TABLE {quote(tabela)} ENABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0010_documentoprocesso"),
        ("accounts", "0003_tokenapi"),
        ("organizations", "0002_conviteescritorio"),
        ("token_blacklist", "0013_alter_blacklistedtoken_options_and_more"),
    ]

    operations = [
        migrations.RunPython(
            restringir_tabelas_do_django,
            reverse_code=migrations.RunPython.noop,
        )
    ]
