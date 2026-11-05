from django.conf import settings
from django.core.mail import send_mail


def uma_linha(texto):
    """Sem quebra de linha: ela é proibida no assunto do e-mail e faria o envio falhar."""
    return " ".join(texto.split())


def enviar_convite(*, convite, token):
    """Envia o link de convite. É o único ponto que conhece o texto do e-mail."""
    link = f"{settings.FRONTEND_URL}/convite?token={token}"
    send_mail(
        subject=f"Convite para o escritório {uma_linha(convite.escritorio.nome)} no JuriPredict",
        message=(
            f"Você foi convidado para participar do escritório "
            f"{convite.escritorio.nome} no JuriPredict.\n\n"
            f"Para aceitar, acesse:\n{link}\n\n"
            f"O convite expira em {convite.expira_em:%d/%m/%Y}. "
            f"Se você não esperava este convite, ignore esta mensagem."
        ),
        from_email=None,
        recipient_list=[convite.email],
    )
