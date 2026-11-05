from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from organizations.models import Escritorio, MembroEscritorio

from .lembretes import enviar_lembretes
from .models import EventoAgenda

User = get_user_model()


class LembretesTests(TestCase):
    def setUp(self):
        self.agora = timezone.now()
        self.usuario = User.objects.create_user(
            username="ana", email="ana@x.com", password="x", first_name="Ana"
        )
        self.escritorio = Escritorio.objects.create(
            nome="Banca", criado_por=self.usuario, fuso_horario="America/Sao_Paulo"
        )
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.usuario, papel="ADVOGADO"
        )

    def _evento(self, *, em=timedelta(hours=5), **extra):
        dados = dict(
            escritorio=self.escritorio,
            usuario=self.usuario,
            titulo="Contestação",
            tipo="PRAZO",
            inicio=self.agora + em,
        )
        dados.update(extra)
        return EventoAgenda.objects.create(**dados)

    def test_envia_um_email_por_pessoa_agrupando_os_eventos(self):
        a = self._evento(titulo="Contestação")
        b = self._evento(titulo="Audiência una", tipo="AUDIENCIA", em=timedelta(hours=8))

        avisados = enviar_lembretes(agora=self.agora)

        self.assertEqual(avisados, 2)
        self.assertEqual(len(mail.outbox), 1)
        corpo = mail.outbox[0].body
        self.assertIn("Contestação", corpo)
        self.assertIn("Audiência una", corpo)
        a.refresh_from_db()
        b.refresh_from_db()
        self.assertIsNotNone(a.lembrete_enviado_em)
        self.assertIsNotNone(b.lembrete_enviado_em)

    def test_nao_avisa_duas_vezes_o_mesmo_evento(self):
        self._evento()

        enviar_lembretes(agora=self.agora)
        segunda = enviar_lembretes(agora=self.agora)

        self.assertEqual(segunda, 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_horario_no_corpo_segue_o_fuso_do_escritorio(self):
        self.escritorio.fuso_horario = "America/Manaus"  # UTC-4, sem horário de verão
        self.escritorio.save()
        inicio = self.agora.replace(hour=15, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self._evento(inicio=inicio)

        enviar_lembretes(agora=inicio - timedelta(hours=2))

        self.assertIn("às 11:00", mail.outbox[0].body)

    def test_ignora_o_que_nao_deve_avisar(self):
        self._evento(concluido=True)
        self._evento(tipo="REUNIAO")
        self._evento(tipo="OUTRO")
        self._evento(em=timedelta(hours=48))  # longe demais
        self._evento(em=-timedelta(hours=10))  # passou além da tolerância

        self.assertEqual(enviar_lembretes(agora=self.agora), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_aviso_atrasado_ainda_sai_dentro_da_tolerancia(self):
        self._evento(em=-timedelta(hours=3))

        self.assertEqual(enviar_lembretes(agora=self.agora), 1)

    def test_ignora_usuario_inativo_ou_sem_email_e_evento_sem_responsavel(self):
        inativo = User.objects.create_user(username="i", email="i@x.com", password="x", is_active=False)
        sem_email = User.objects.create_user(username="s", email="", password="x")
        for usuario in (inativo, sem_email):
            MembroEscritorio.objects.create(
                escritorio=self.escritorio, usuario=usuario, papel="ADVOGADO"
            )
            self._evento(usuario=usuario)
        self._evento(usuario=None)

        self.assertEqual(enviar_lembretes(agora=self.agora), 0)

    def test_quem_saiu_do_escritorio_nao_recebe_a_agenda_dele(self):
        self._evento()
        MembroEscritorio.objects.update(status=MembroEscritorio.Status.SUSPENSO)

        self.assertEqual(enviar_lembretes(agora=self.agora), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_escritorio_desativado_nao_gera_aviso(self):
        self._evento()
        Escritorio.objects.update(ativo=False)

        self.assertEqual(enviar_lembretes(agora=self.agora), 0)

    def test_falha_de_um_destinatario_nao_trava_os_outros_e_nao_marca_o_evento(self):
        outro = User.objects.create_user(username="bia", email="bia@x.com", password="x")
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=outro, papel="ADVOGADO"
        )
        quebrado = self._evento(usuario=self.usuario)
        saudavel = self._evento(usuario=outro)

        def enviar(*, usuario, escritorio, eventos):
            if usuario == self.usuario:
                raise ConnectionError("SMTP fora do ar")
            mail.send_mail("s", "m", None, [usuario.email])

        with self.assertLogs("api.lembretes", level="ERROR"):
            avisados = enviar_lembretes(agora=self.agora, enviar=enviar)

        self.assertEqual(avisados, 1)
        quebrado.refresh_from_db()
        saudavel.refresh_from_db()
        self.assertIsNone(quebrado.lembrete_enviado_em)  # tenta de novo na próxima
        self.assertIsNotNone(saudavel.lembrete_enviado_em)

    def test_evento_vinculado_cita_o_processo(self):
        from .models import Cliente, Processo

        cliente = Cliente.objects.create(
            escritorio=self.escritorio, usuario=self.usuario, nome="Cli", cpf_cnpj="x"
        )
        processo = Processo.objects.create(
            escritorio=self.escritorio,
            usuario=self.usuario,
            cliente=cliente,
            numero_cnj="0001234-56.2026.5.16.0001",
            vara="1ª Vara",
            comarca="São Luís",
            parte_contraria="Empresa",
        )
        self._evento(processo=processo)

        enviar_lembretes(agora=self.agora)

        self.assertIn("0001234-56.2026.5.16.0001", mail.outbox[0].body)
