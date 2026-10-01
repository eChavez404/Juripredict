import os

from cryptography.fernet import InvalidToken
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.crypto_utils import get_fernet, hash_data_with_key
from api.models import Cliente


class Command(BaseCommand):
    help = "Recriptografa documentos de clientes usando FIELD_ENCRYPTION_KEY."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida todos os registros sem persistir alterações.",
        )

    def handle(self, *args, **options):
        old_secret = os.getenv("OLD_FIELD_ENCRYPTION_KEY", "")
        new_secret = settings.FIELD_ENCRYPTION_KEY

        if not old_secret:
            raise CommandError("Defina OLD_FIELD_ENCRYPTION_KEY no ambiente.")
        if old_secret == new_secret:
            raise CommandError("A chave antiga e a nova chave devem ser diferentes.")

        old_fernet = get_fernet(old_secret)
        new_fernet = get_fernet(new_secret)

        with transaction.atomic():
            clientes = list(Cliente.objects.select_for_update().order_by("pk"))
            atualizacoes = []

            for cliente in clientes:
                try:
                    documento = old_fernet.decrypt(
                        cliente.cpf_cnpj.encode("utf-8")
                    ).decode("utf-8")
                except (InvalidToken, UnicodeDecodeError) as exc:
                    raise CommandError(
                        f"Não foi possível validar o documento do cliente {cliente.pk}. "
                        "Nenhuma alteração foi persistida."
                    ) from exc

                cliente.cpf_cnpj = new_fernet.encrypt(
                    documento.encode("utf-8")
                ).decode("utf-8")
                cliente.cpf_cnpj_hash = hash_data_with_key(documento, new_secret)
                atualizacoes.append(cliente)

            if options["dry_run"]:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Validação concluída para {len(atualizacoes)} cliente(s); "
                        "nenhuma alteração foi persistida."
                    )
                )
                return

            Cliente.objects.bulk_update(
                atualizacoes,
                fields=("cpf_cnpj", "cpf_cnpj_hash"),
                batch_size=500,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Chave rotacionada para {len(atualizacoes)} cliente(s)."
            )
        )
