import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.jurimetria_tribunal import estado_da_validacao, importar


class Command(BaseCommand):
    help = (
        "Importa a base da jurimetria do tribunal, gerada por "
        "dataset/pipeline/exportar_jurimetria.py. Substitui a base anterior."
    )

    def add_arguments(self, parser):
        parser.add_argument("arquivo", help="CSV do exportar_jurimetria.py")
        parser.add_argument(
            "--validacao",
            help="JSON com o gold set e a cobertura medidos; sem ele as taxas ficam suprimidas",
        )

    def handle(self, *args, **options):
        validacao = None
        if options["validacao"]:
            validacao = json.loads(Path(options["validacao"]).read_text(encoding="utf-8"))
        try:
            with open(options["arquivo"], encoding="utf-8", newline="") as arquivo:
                lote = importar(arquivo, validacao=validacao)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        estado = estado_da_validacao(lote)
        self.stdout.write(f"{lote.total} decisões importadas (versão {lote.versao}).")
        self.stdout.write(
            "Taxas liberadas." if estado["rotulo_conferido"] else f"Taxas suprimidas: {estado['motivo']}"
        )
