from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from corsheaders.signals import check_request_enabled

        check_request_enabled.connect(_cors_do_protocolo_oauth)


def _cors_do_protocolo_oauth(sender, request, **kwargs):
    """Libera CORS só no protocolo OAuth: clientes MCP que rodam no navegador (o MCP
    Inspector, por exemplo) precisam registrar-se e trocar tokens. Nada ali usa cookie."""
    return request.path.startswith(("/oauth/", "/.well-known/"))
