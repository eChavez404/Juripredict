from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import send_mail

from organizations.emails import corpo_html, uma_linha

ROTULOS = {"AUDIENCIA": "Audiência", "PRAZO": "Prazo"}
FONTE_DATAJUD = "Fonte: DataJud (CNJ), que pode atrasar em relação ao tribunal."


def enviar_lembrete_prazos(*, usuario, escritorio, eventos):
    """Um e-mail por pessoa e escritório, com o horário no fuso do escritório."""
    fuso = ZoneInfo(escritorio.fuso_horario)
    itens = []
    for evento in eventos:
        quando = evento.inicio.astimezone(fuso).strftime("%d/%m/%Y às %H:%M")
        rotulo = ROTULOS.get(evento.tipo, evento.get_tipo_display())
        processo = f" (processo {evento.processo.numero_cnj})" if evento.processo_id else ""
        itens.append(f"{rotulo}: {evento.titulo}{processo} — {quando}")

    plural = len(eventos) > 1
    saudacao = f"Olá, {usuario.first_name or usuario.email}."
    aviso = (
        f"{'Estes compromissos estão próximos' if plural else 'Este compromisso está próximo'} "
        f"no escritório {escritorio.nome}:"
    )
    rodape = "Marque como concluído na agenda para não receber novos avisos."
    send_mail(
        subject=f"{'Compromissos próximos' if plural else 'Compromisso próximo'} — {uma_linha(escritorio.nome)}",
        message=f"{saudacao}\n\n{aviso}\n\n" + "\n".join(f"- {item}" for item in itens) + f"\n\n{rodape}",
        from_email=None,
        recipient_list=[usuario.email],
        html_message=corpo_html(
            titulo="Compromissos próximos" if plural else "Compromisso próximo",
            paragrafos=[saudacao, aviso],
            blocos=[(None, itens)],
            botao=("Abrir agenda", f"{settings.FRONTEND_URL}/agenda"),
            nota=rodape,
        ),
    )


def enviar_novos_andamentos(*, usuario, escritorio, itens):
    """Um e-mail por pessoa e escritório, com os andamentos novos de cada processo.

    ``itens`` é uma lista de ``(processo, andamentos)``.
    """
    fuso = ZoneInfo(escritorio.fuso_horario)
    blocos = []
    for processo, andamentos in itens:
        linhas = [
            f"{a.data_hora.astimezone(fuso).strftime('%d/%m/%Y')}: {a.nome}"
            for a in andamentos[:10]
        ]
        if len(andamentos) > 10:
            linhas.append(f"e mais {len(andamentos) - 10}")
        blocos.append((f"Processo {processo.numero_cnj}", linhas))

    saudacao = f"Olá, {usuario.first_name or usuario.email}."
    aviso = f"Encontramos andamentos novos no escritório {escritorio.nome}:"
    send_mail(
        subject=f"Novos andamentos — {uma_linha(escritorio.nome)}",
        message=(
            f"{saudacao}\n\n{aviso}\n\n"
            + "\n\n".join(titulo + "\n" + "\n".join(f"  - {linha}" for linha in linhas) for titulo, linhas in blocos)
            + f"\n\n{FONTE_DATAJUD}"
        ),
        from_email=None,
        recipient_list=[usuario.email],
        html_message=corpo_html(
            titulo="Novos andamentos",
            paragrafos=[saudacao, aviso],
            blocos=blocos,
            botao=("Ver processos", f"{settings.FRONTEND_URL}/processos"),
            nota=FONTE_DATAJUD,
        ),
    )
