from django.conf import settings
from django.core.mail import send_mail


def enviar_reset_senha(*, usuario, uid, token):
    """Envia o link de redefinição. O link vale por ``PASSWORD_RESET_TIMEOUT``."""
    link = f"{settings.FRONTEND_URL}/redefinir-senha?uid={uid}&token={token}"
    minutos = settings.PASSWORD_RESET_TIMEOUT // 60
    send_mail(
        subject="Redefinição de senha do JuriPredict",
        message=(
            "Recebemos um pedido para redefinir a senha da sua conta.\n\n"
            f"Para criar uma nova senha, acesse:\n{link}\n\n"
            f"O link vale por {minutos} minutos e só pode ser usado uma vez. "
            "Se você não fez este pedido, ignore esta mensagem: sua senha continua a mesma."
        ),
        from_email=None,
        recipient_list=[usuario.email],
    )


def enviar_verificacao_email(*, usuario, token):
    """Envia o link de confirmação do e-mail."""
    link = f"{settings.FRONTEND_URL}/confirmar-email?token={token}"
    horas = settings.VERIFICACAO_EMAIL_HORAS
    send_mail(
        subject="Confirme seu e-mail no JuriPredict",
        message=(
            "Para confirmar que este e-mail é seu, acesse:\n"
            f"{link}\n\n"
            f"O link vale por {horas} horas. "
            "Se você não criou uma conta, ignore esta mensagem."
        ),
        from_email=None,
        recipient_list=[usuario.email],
    )
