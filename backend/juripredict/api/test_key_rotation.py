import os
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from organizations.models import Escritorio

from .crypto_utils import get_fernet, hash_data_with_key
from .models import Cliente


class RotateFieldEncryptionKeyTests(TestCase):
    old_secret = "chave-antiga-de-teste"
    new_secret = "chave-nova-de-teste"
    documento = "12345678900"

    def setUp(self):
        usuario = get_user_model().objects.create_user(username="gestor")
        escritorio = Escritorio.objects.create(nome="Escritório", criado_por=usuario)
        self.cliente = Cliente.objects.create(
            usuario=usuario,
            escritorio=escritorio,
            nome="Cliente",
            cpf_cnpj=get_fernet(self.old_secret)
            .encrypt(self.documento.encode("utf-8"))
            .decode("utf-8"),
            cpf_cnpj_hash=hash_data_with_key(self.documento, self.old_secret),
        )

    @override_settings(FIELD_ENCRYPTION_KEY=new_secret)
    def test_rotaciona_criptografia_e_hash_sem_expor_documento(self):
        output = StringIO()

        with patch.dict(
            os.environ, {"OLD_FIELD_ENCRYPTION_KEY": self.old_secret}, clear=False
        ):
            call_command("rotate_field_encryption_key", stdout=output)

        self.cliente.refresh_from_db()
        documento = (
            get_fernet(self.new_secret)
            .decrypt(self.cliente.cpf_cnpj.encode("utf-8"))
            .decode("utf-8")
        )
        self.assertEqual(documento, self.documento)
        self.assertEqual(
            self.cliente.cpf_cnpj_hash,
            hash_data_with_key(self.documento, self.new_secret),
        )
        self.assertNotIn(self.documento, output.getvalue())

    @override_settings(FIELD_ENCRYPTION_KEY=new_secret)
    def test_dry_run_valida_sem_persistir(self):
        valor_original = self.cliente.cpf_cnpj

        with patch.dict(
            os.environ, {"OLD_FIELD_ENCRYPTION_KEY": self.old_secret}, clear=False
        ):
            call_command("rotate_field_encryption_key", "--dry-run")

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.cpf_cnpj, valor_original)

    @override_settings(FIELD_ENCRYPTION_KEY=new_secret)
    def test_aborta_quando_um_registro_nao_pode_ser_decifrado(self):
        self.cliente.cpf_cnpj = "token-invalido"
        self.cliente.save(update_fields=("cpf_cnpj",))

        with patch.dict(
            os.environ, {"OLD_FIELD_ENCRYPTION_KEY": self.old_secret}, clear=False
        ):
            with self.assertRaises(CommandError):
                call_command("rotate_field_encryption_key")

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.cpf_cnpj, "token-invalido")
