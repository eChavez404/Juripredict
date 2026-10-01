from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class EscritorioBackfillMigrationTests(TransactionTestCase):
    migrate_from = [("api", "0003_add_escritorio_nullable")]
    migrate_to = [("api", "0007_harden_supabase_access")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        Usuario = old_apps.get_model("auth", "User")
        Cliente = old_apps.get_model("api", "Cliente")
        Processo = old_apps.get_model("api", "Processo")
        EventoAgenda = old_apps.get_model("api", "EventoAgenda")

        usuario = Usuario.objects.create(username="legado", email="legado@example.com")
        cliente = Cliente.objects.create(
            usuario_id=usuario.pk,
            nome="Cliente legado",
            cpf_cnpj="valor-legado",
            cpf_cnpj_hash="hash-legado",
            tipo="PF",
        )
        processo = Processo.objects.create(
            usuario_id=usuario.pk,
            numero_cnj="0010234-56.2024.5.16.0001",
            vara="1ª Vara",
            comarca="Balsas",
            cliente_id=cliente.pk,
            parte_contraria="Parte contrária",
        )
        EventoAgenda.objects.create(
            usuario_id=usuario.pk,
            processo_id=processo.pk,
            titulo="Evento legado",
            inicio="2026-09-29T12:00:00Z",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def test_cria_escritorio_owner_e_preserva_relacoes(self):
        Escritorio = self.apps.get_model("organizations", "Escritorio")
        Membro = self.apps.get_model("organizations", "MembroEscritorio")
        Cliente = self.apps.get_model("api", "Cliente")
        Processo = self.apps.get_model("api", "Processo")
        Evento = self.apps.get_model("api", "EventoAgenda")

        escritorio = Escritorio.objects.get()
        membro = Membro.objects.get()

        self.assertEqual(membro.escritorio_id, escritorio.pk)
        self.assertEqual(membro.papel, "OWNER")
        self.assertEqual(membro.status, "ATIVO")
        self.assertEqual(Cliente.objects.get().escritorio_id, escritorio.pk)
        self.assertEqual(Processo.objects.get().escritorio_id, escritorio.pk)
        self.assertEqual(Evento.objects.get().escritorio_id, escritorio.pk)

