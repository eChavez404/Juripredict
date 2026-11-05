from django.core.management.base import BaseCommand

from api.andamentos import sincronizar_todos


class Command(BaseCommand):
    help = (
        "Lê no DataJud os andamentos dos processos ativos. "
        "Agende uma vez por dia (cron ou Render Cron Job)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limite", type=int, default=200, help="máximo de processos por rodada")

    def handle(self, *args, **options):
        resumo = sincronizar_todos(limite=options["limite"])
        self.stdout.write(
            f"{resumo['processos']} processo(s) lido(s), "
            f"{resumo['novos']} andamento(s) novo(s), {resumo['falhas']} falha(s), "
            f"{resumo['avisados']} pessoa(s) avisada(s)."
        )
