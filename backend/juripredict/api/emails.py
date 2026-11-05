from zoneinfo import ZoneInfo

from django.core.mail import send_mail

from organizations.emails import uma_linha

ROTULOS = {"AUDIENCIA": "Audiência", "PRAZO": "Prazo"}


def enviar_lembrete_prazos(*, usuario, escritorio, eventos):
    """Um e-mail por pessoa e escritório, com o horário no fuso do escritório."""
    fuso = ZoneInfo(escritorio.fuso_horario)
    linhas = []
    for evento in eventos:
        quando = evento.inicio.astimezone(fuso).strftime("%d/%m/%Y às %H:%M")
        rotulo = ROTULOS.get(evento.tipo, evento.get_tipo_display())
        processo = f" (processo {evento.processo.numero_cnj})" if evento.processo_id else ""
        linhas.append(f"- {rotulo}: {evento.titulo}{processo} — {quando}")

    plural = len(eventos) > 1
    send_mail(
        subject=f"{'Compromissos próximos' if plural else 'Compromisso próximo'} — {uma_linha(escritorio.nome)}",
        message=(
            f"Olá, {usuario.first_name or usuario.email}.\n\n"
            f"{'Estes compromissos estão' if plural else 'Este compromisso está'} "
            f"próximo no escritório {escritorio.nome}:\n\n" + "\n".join(linhas) +
            "\n\nMarque como concluído na agenda para não receber novos avisos."
        ),
        from_email=None,
        recipient_list=[usuario.email],
    )


def enviar_novos_andamentos(*, usuario, escritorio, itens):
    """Um e-mail por pessoa e escritório, com os andamentos novos de cada processo.

    ``itens`` é uma lista de ``(processo, andamentos)``.
    """
    fuso = ZoneInfo(escritorio.fuso_horario)
    blocos = []
    for processo, andamentos in itens:
        linhas = [
            f"  - {a.data_hora.astimezone(fuso).strftime('%d/%m/%Y')}: {a.nome}"
            for a in andamentos[:10]
        ]
        if len(andamentos) > 10:
            linhas.append(f"  - e mais {len(andamentos) - 10}")
        blocos.append(f"Processo {processo.numero_cnj}\n" + "\n".join(linhas))

    send_mail(
        subject=f"Novos andamentos — {uma_linha(escritorio.nome)}",
        message=(
            f"Olá, {usuario.first_name or usuario.email}.\n\n"
            f"Encontramos andamentos novos no escritório {escritorio.nome}:\n\n"
            + "\n\n".join(blocos)
            + "\n\nFonte: DataJud (CNJ), que pode atrasar em relação ao tribunal."
        ),
        from_email=None,
        recipient_list=[usuario.email],
    )
