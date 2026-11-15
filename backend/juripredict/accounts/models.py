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
    # Preenchido quando o token foi emitido por OAuth (ver ``accounts.oauth``): ele
    # vale pouco tempo e só enxerga o escritório escolhido na tela de consentimento.
    conexao = models.ForeignKey(
        "ConexaoOAuth", on_delete=models.CASCADE, null=True, blank=True, related_name="tokens"
    )

    class Meta:
        ordering = ("-criado_em",)

    @property
    def ativo(self):
        from django.utils import timezone

        return self.revogado_em is None and self.expira_em > timezone.now()

    def __str__(self):
        return f"{self.nome} ({self.prefixo}…)"


class ClienteOAuth(models.Model):
    """Aplicativo que se registrou para pedir acesso (o Claude, o agente do JuriPredict).

    Registrado por DCR (RFC 7591). O público prova a posse do pedido com PKCE; o
    confidencial também tem segredo, guardado só como hash.
    """

    class Autenticacao(models.TextChoices):
        NENHUMA = "none", "Cliente público"
        SEGREDO_POST = "client_secret_post", "Segredo no corpo"
        SEGREDO_BASIC = "client_secret_basic", "Segredo no cabeçalho"

    client_id = models.CharField(max_length=64, unique=True)
    nome = models.CharField(max_length=120)
    redirect_uris = models.JSONField()
    autenticacao = models.CharField(
        max_length=24, choices=Autenticacao.choices, default=Autenticacao.NENHUMA
    )
    segredo_hash = models.CharField(max_length=64, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nome


class ConexaoOAuth(models.Model):
    """Autorização que uma pessoa deu a um aplicativo, para UM escritório.

    É o que aparece em "Aplicativos conectados". Revogá-la derruba na hora todos os
    tokens emitidos por ela.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conexoes_oauth"
    )
    cliente = models.ForeignKey(ClienteOAuth, on_delete=models.CASCADE, related_name="conexoes")
    escritorio = models.ForeignKey(
        "organizations.Escritorio", on_delete=models.CASCADE, related_name="conexoes_oauth"
    )
    # o servidor MCP para o qual os tokens valem (RFC 8707)
    recurso = models.URLField(max_length=300)
    criado_em = models.DateTimeField(auto_now_add=True)
    revogada_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-criado_em",)

    @property
    def ativa(self):
        return self.revogada_em is None

    def __str__(self):
        return f"{self.cliente} → {self.escritorio}"


class CodigoAutorizacao(models.Model):
    """Código de uso único devolvido ao aplicativo depois do consentimento."""

    conexao = models.ForeignKey(ConexaoOAuth, on_delete=models.CASCADE, related_name="codigos")
    hash = models.CharField(max_length=64, unique=True)
    redirect_uri = models.TextField()
    code_challenge = models.CharField(max_length=128)
    expira_em = models.DateTimeField()
    usado_em = models.DateTimeField(null=True, blank=True)


class RenovacaoOAuth(models.Model):
    """Refresh token. Cada uso emite um novo e inutiliza este; usar de novo um que
    já foi trocado indica roubo, e a conexão inteira é revogada."""

    conexao = models.ForeignKey(ConexaoOAuth, on_delete=models.CASCADE, related_name="renovacoes")
    hash = models.CharField(max_length=64, unique=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    expira_em = models.DateTimeField()
    usado_em = models.DateTimeField(null=True, blank=True)
