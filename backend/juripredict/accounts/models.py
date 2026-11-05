from django.conf import settings
from django.db import models


class AceiteTermos(models.Model):
    """Registro de que o usuário aceitou uma versão dos termos e da política.

    Serve de prova de consentimento, por isso não se apaga com a conta: a
    exclusão anonimiza o usuário (ver ``accounts.services.excluir_conta``) e o
    aceite permanece vinculado a ele.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="aceites_termos",
    )
    versao = models.CharField(max_length=20)
    aceito_em = models.DateTimeField(auto_now_add=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ("-aceito_em",)
        constraints = [
            models.UniqueConstraint(
                fields=("usuario", "versao"), name="aceite_unico_por_versao"
            )
        ]

    def __str__(self):
        return f"{self.usuario} aceitou {self.versao}"


class EmailVerificado(models.Model):
    """Existe uma linha quando o usuário provou controlar o e-mail da conta.

    O login não depende disso: sem SMTP configurado, exigir verificação
    trancaria todos para fora. O app mostra um aviso até a confirmação.
    """

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verificado",
    )
    verificado_em = models.DateTimeField(auto_now_add=True)


class TokenApi(models.Model):
    """Credencial de longa duração para agentes (MCP), separada da senha.

    Só o hash fica no banco. Dá acesso SOMENTE LEITURA, a um conjunto fixo de rotas
    (ver ``accounts.authentication``), e cada uso entra na auditoria do escritório.
    Pode ser revogada a qualquer momento sem afetar a senha nem as sessões da pessoa.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tokens_api"
    )
    nome = models.CharField(max_length=80)
    # começo do token, só para a pessoa reconhecer qual é qual na lista
    prefixo = models.CharField(max_length=12)
    hash = models.CharField(max_length=64, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    ultimo_uso_em = models.DateTimeField(null=True, blank=True)
    revogado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-criado_em",)

    @property
    def ativo(self):
        from django.utils import timezone

        return self.revogado_em is None and self.expira_em > timezone.now()

    def __str__(self):
        return f"{self.nome} ({self.prefixo}…)"
