from django.core.management.base import BaseCommand

from api.lembretes import enviar_lembretes


class Command(BaseCommand):
    help = (
        "Envia por e-mail os lembretes de prazos e audiências próximos. "
        "Agende de hora em hora (cron ou Render Cron Job)."
    )

    def handle(self, *args, **options):
        avisados = enviar_lembretes()
        self.stdout.write(f"{avisados} compromisso(s) avisado(s).")
