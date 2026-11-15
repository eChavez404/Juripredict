from django.conf import settings
from django.core.mail import send_mail
from django.utils.html import escape

FONTE = "'Poppins','Segoe UI',Helvetica,Arial,sans-serif"


def uma_linha(texto):
    """Sem quebra de linha: ela é proibida no assunto do e-mail e faria o envio falhar."""
    return " ".join(texto.split())


def corpo_html(*, titulo, paragrafos=(), botao=None, blocos=(), nota=None):
    """Versão HTML do e-mail, com as cores do app. O texto simples continua sendo
    enviado junto, para quem não exibe HTML.

    Tabelas e estilo inline porque é o que os clientes de e-mail respeitam. Todo
    texto passa por ``escape``: nome de escritório e título de compromisso vêm de
    quem usa o sistema. ``botao`` é ``(rótulo, link)``; ``blocos`` é uma lista de
    ``(título ou None, [linhas])``.
    """
    partes = [f'<h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;color:#19333b">{escape(titulo)}</h1>']
    partes += [f'<p style="margin:0 0 16px">{escape(p)}</p>' for p in paragrafos]
    for cabecalho, linhas in blocos:
        topo = f'<p style="margin:0 0 8px;font-weight:600">{escape(cabecalho)}</p>' if cabecalho else ""
        itens = "".join(f'<li style="margin:0 0 6px">{escape(linha)}</li>' for linha in linhas)
        partes.append(
            '<div style="margin:0 0 16px;padding:16px 20px;background:#f8fcfd;'
            f'border:1px solid #dcebed;border-radius:10px">{topo}'
            f'<ul style="margin:0;padding-left:18px">{itens}</ul></div>'
        )
    if botao:
        rotulo, link = escape(botao[0]), escape(botao[1])
        partes.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 24px"><tr>'
            '<td style="border-radius:10px;background:#0891b2">'
            f'<a href="{link}" style="display:inline-block;padding:13px 28px;font-weight:600;'
            f'color:#ffffff;text-decoration:none">{rotulo}</a></td></tr></table>'
            '<p style="margin:0 0 16px;font-size:13px;color:#688088">'
            'Se o botão não funcionar, copie este endereço no navegador:<br>'
            f'<a href="{link}" style="color:#0891b2;word-break:break-all">{link}</a></p>'
        )
    if nota:
        partes.append(
            '<p style="margin:24px 0 0;padding-top:16px;border-top:1px solid #dcebed;'
            f'font-size:13px;color:#688088">{escape(nota)}</p>'
        )
    resumo = escape(paragrafos[0]) if paragrafos else ""
    return (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="light"><title>{escape(titulo)}</title></head>'
        '<body style="margin:0;padding:0;background:#f4fafb">'
        f'<div style="display:none;max-height:0;overflow:hidden">{resumo}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4fafb">'
        '<tr><td align="center" style="padding:32px 16px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:560px;background:#ffffff;border:1px solid #bce5eb;border-radius:16px">'
        f'<tr><td style="padding:22px 32px;border-bottom:1px solid #e1f5f8;font-family:{FONTE}">'
        '<span style="font-size:20px;font-weight:700;color:#0891b2">JuriPredict</span>'
        '<span style="font-size:13px;color:#8da0a6"> &nbsp;Jurimetria trabalhista</span></td></tr>'
        f'<tr><td style="padding:32px;font-family:{FONTE};font-size:16px;line-height:1.6;color:#19333b">'
        + "".join(partes) +
        '</td></tr></table>'
        f'<p style="margin:16px 0 0;font-family:{FONTE};font-size:12px;color:#8da0a6">'
        'Mensagem automática do JuriPredict. Não responda a este e-mail.</p>'
        '</td></tr></table></body></html>'
    )


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
        html_message=corpo_html(
            titulo="Você foi convidado",
            paragrafos=[f"Você foi convidado para participar do escritório {convite.escritorio.nome} no JuriPredict."],
            botao=("Aceitar convite", link),
            nota=(
                f"O convite expira em {convite.expira_em:%d/%m/%Y}. "
                "Se você não esperava este convite, ignore esta mensagem."
            ),
        ),
    )
