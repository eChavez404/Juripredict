from django.conf import settings
from django.core.mail import send_mail

from organizations.emails import corpo_html


def enviar_reset_senha(*, usuario, uid, token):
    """Envia o link de redefinição. O link vale por ``PASSWORD_RESET_TIMEOUT``."""
    link = f"{settings.FRONTEND_URL}/redefinir-senha?uid={uid}&token={token}"
    minutos = settings.PASSWORD_RESET_TIMEOUT // 60
    validade = (
        f"O link vale por {minutos} minutos e só pode ser usado uma vez. "
        "Se você não fez este pedido, ignore esta mensagem: sua senha continua a mesma."
    )
    send_mail(
        subject="Redefinição de senha do JuriPredict",
        message=(
            "Recebemos um pedido para redefinir a senha da sua conta.\n\n"
            f"Para criar uma nova senha, acesse:\n{link}\n\n{validade}"
        ),
        from_email=None,
        recipient_list=[usuario.email],
        html_message=corpo_html(
            titulo="Redefinir sua senha",
            paragrafos=["Recebemos um pedido para redefinir a senha da sua conta."],
            botao=("Criar nova senha", link),
            nota=validade,
        ),
    )


def enviar_verificacao_email(*, usuario, token):
    """Envia o link de confirmação do e-mail."""
    link = f"{settings.FRONTEND_URL}/confirmar-email?token={token}"
    validade = (
        f"O link vale por {settings.VERIFICACAO_EMAIL_HORAS} horas. "
        "Se você não criou uma conta, ignore esta mensagem."
    )
    send_mail(
        subject="Confirme seu e-mail no JuriPredict",
        message=f"Para confirmar que este e-mail é seu, acesse:\n{link}\n\n{validade}",
        from_email=None,
        recipient_list=[usuario.email],
        html_message=corpo_html(
            titulo="Confirme seu e-mail",
            paragrafos=["Falta só confirmar que este e-mail é seu para concluir o cadastro."],
            botao=("Confirmar e-mail", link),
            nota=validade,
        ),
    )
