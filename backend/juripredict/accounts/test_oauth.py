"""Conector MCP remoto: o servidor de autorização OAuth 2.1 de ``accounts.oauth``.

É um fluxo de autorização, então os testes cobrem sobretudo o que NÃO pode acontecer:
redirecionar para endereço não registrado, aceitar PKCE errado, reaproveitar código ou
refresh token, escrever na API, enxergar outro escritório, sobreviver à revogação.
"""

import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import ConexaoOAuth, RenovacaoOAuth
from accounts.tokens_api import criar_token_api, revogar_tokens_api
from api.models import Cliente, Processo
from auditlog.models import EventoAuditoria
from organizations.models import Escritorio, MembroEscritorio

User = get_user_model()
SENHA = "uma-senha-bem-forte-123"
REDIRECT = "https://claude.exemplo.invalid/callback"
RECURSO = "https://mcp.exemplo.invalid/mcp"
SEGREDO = "segredo-de-introspeccao"


def _pkce():
    verificador = secrets.token_urlsafe(48)
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
    return verificador, desafio.rstrip(b"=").decode()


@override_settings(
    OAUTH_EMISSOR="https://app.exemplo.invalid",
    OAUTH_RECURSOS=[RECURSO],
    OAUTH_SEGREDO_INTROSPECCAO=SEGREDO,
)
class ConectorOAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.ana = User.objects.create_user(username="ana@x.com", email="ana@x.com", password=SENHA)
        self.escritorio = Escritorio.objects.create(nome="Banca da Ana", criado_por=self.ana)
        self.membro = MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.ana, papel="OWNER"
        )
        self.processo = self._processo(self.escritorio, self.ana, "0000001")

        bia = User.objects.create_user(username="bia@x.com", email="bia@x.com", password=SENHA)
        self.outro = Escritorio.objects.create(nome="Outra banca", criado_por=bia)
        MembroEscritorio.objects.create(escritorio=self.outro, usuario=bia, papel="OWNER")
        self._processo(self.outro, bia, "0000002")
        # Ana também é membro da outra banca: o token não pode enxergá-la mesmo assim
        MembroEscritorio.objects.create(escritorio=self.outro, usuario=self.ana, papel="ADVOGADO")
        self.anonimo = APIClient()

    def _processo(self, escritorio, usuario, numero):
        cliente = Cliente.objects.create(escritorio=escritorio, usuario=usuario, nome="C", cpf_cnpj=numero)
        return Processo.objects.create(
            escritorio=escritorio, usuario=usuario, cliente=cliente,
            numero_cnj=f"{numero}-00.2024.5.16.0001", vara="V", comarca="C", parte_contraria="X",
        )

    # ------------------------------------------------------------ ajudantes do fluxo
    def _sessao(self):
        cliente = APIClient()
        cliente.force_authenticate(self.ana)
        return cliente

    def _form(self, url, dados, **cabecalhos):
        return self.anonimo.post(
            url, urlencode(dados), content_type="application/x-www-form-urlencoded", **cabecalhos
        )

    def _registrar(self, **extra):
        resposta = self.anonimo.post(
            "/oauth/registrar", {"client_name": "Claude", "redirect_uris": [REDIRECT], **extra}, format="json"
        )
        self.assertEqual(resposta.status_code, 201, resposta.data)
        return resposta.data

    def _pedido(self, client_id, desafio, **extra):
        return {
            "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
            "code_challenge": desafio, "code_challenge_method": "S256", "state": "estado-1",
            "resource": RECURSO, **extra,
        }

    def _autorizar(self, client_id, desafio, escritorio=None):
        resposta = self._sessao().post(
            "/api/v1/oauth/pedido/",
            {**self._pedido(client_id, desafio), "permitir": True,
             "escritorio_id": str((escritorio or self.escritorio).pk)},
            format="json",
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        return parse_qs(urlsplit(resposta.data["redirecionar"]).query)

    def _trocar(self, client_id, codigo, verificador, **cabecalhos):
        return self._form("/oauth/token", {
            "grant_type": "authorization_code", "client_id": client_id, "code": codigo,
            "redirect_uri": REDIRECT, "code_verifier": verificador,
        }, **cabecalhos)

    def _conectar(self):
        """Fluxo completo; devolve (client_id, resposta do /oauth/token)."""
        client_id = self._registrar()["client_id"]
        verificador, desafio = _pkce()
        codigo = self._autorizar(client_id, desafio)["code"][0]
        resposta = self._trocar(client_id, codigo, verificador)
        self.assertEqual(resposta.status_code, 200, resposta.data)
        return client_id, resposta.data

    def _api(self, token, metodo="get", caminho="/api/v1/processos/", **extra):
        cliente = APIClient()
        cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", **extra)
        return getattr(cliente, metodo)(caminho)

    # ------------------------------------------------------------ fluxo feliz
    def test_metadados_publicam_os_endpoints_e_so_s256(self):
        dados = self.anonimo.get("/.well-known/oauth-authorization-server").json()

        self.assertEqual(dados["issuer"], "https://app.exemplo.invalid")
        self.assertEqual(dados["authorization_endpoint"], "https://app.exemplo.invalid/autorizar")
        self.assertEqual(dados["code_challenge_methods_supported"], ["S256"])

    @override_settings(CORS_ALLOW_ALL_ORIGINS=False, CORS_ALLOWED_ORIGINS=[])
    def test_cors_aberto_so_no_protocolo(self):
        origem = {"HTTP_ORIGIN": "https://inspector.exemplo.invalid"}
        protocolo = self.anonimo.get("/.well-known/oauth-authorization-server", **origem)
        api = self.anonimo.get("/api/v1/processos/", **origem)

        self.assertIn("access-control-allow-origin", protocolo.headers)
        self.assertNotIn("access-control-allow-origin", api.headers)

    def test_fluxo_completo_da_acesso_so_ao_escritorio_autorizado(self):
        client_id = self._registrar()["client_id"]
        verificador, desafio = _pkce()

        tela = self._sessao().get("/api/v1/oauth/pedido/", self._pedido(client_id, desafio))
        self.assertEqual(tela.status_code, 200)
        self.assertEqual(tela.data["aplicativo"], "Claude")
        self.assertEqual(tela.data["destino"], "claude.exemplo.invalid")
        self.assertEqual(len(tela.data["escritorios"]), 2)

        retorno = self._autorizar(client_id, desafio)
        self.assertEqual(retorno["state"], ["estado-1"])
        self.assertEqual(retorno["iss"], ["https://app.exemplo.invalid"])

        resposta = self._trocar(client_id, retorno["code"][0], verificador)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Cache-Control"], "no-store")
        tokens = resposta.data
        self.assertTrue(tokens["access_token"].startswith("jp_"))
        self.assertEqual((tokens["token_type"], tokens["scope"]), ("Bearer", "leitura"))

        # o cabeçalho de outro escritório é ignorado: vale o da conexão
        lista = self._api(tokens["access_token"], HTTP_X_ESCRITORIO_ID=str(self.outro.pk))
        self.assertEqual(lista.status_code, 200)
        self.assertEqual([p["id"] for p in lista.data], [self.processo.pk])

        leitura = EventoAuditoria.objects.get(acao="token_api.leitura")
        self.assertEqual(leitura.escritorio, self.escritorio)
        self.assertEqual(leitura.alteracoes["aplicativo"], "Claude")
        self.assertTrue(EventoAuditoria.objects.filter(acao="oauth.conexao_criada").exists())

    def test_token_oauth_nao_escreve_nem_lista_os_escritorios(self):
        _, tokens = self._conectar()

        self.assertEqual(self._api(tokens["access_token"], "post").status_code, 403)
        self.assertEqual(self._api(tokens["access_token"], caminho="/api/v1/auth/me/").status_code, 403)
        self.assertEqual(self._api(tokens["access_token"], caminho="/api/v1/clientes/").status_code, 403)

    def test_tokens_oauth_ficam_fora_da_lista_manual(self):
        self._conectar()

        self.assertEqual(self._sessao().get("/api/v1/auth/tokens/").data, [])
        self.assertEqual(len(self._sessao().get("/api/v1/auth/conexoes/").data), 1)

    # ------------------------------------------------------------ pedido de autorização
    def test_cliente_ou_redirect_desconhecido_nunca_redireciona(self):
        client_id = self._registrar()["client_id"]
        _, desafio = _pkce()

        for pedido in (
            self._pedido("nao-existe", desafio),
            self._pedido(client_id, desafio, redirect_uri="https://atacante.exemplo.invalid/cb"),
        ):
            resposta = self._sessao().get("/api/v1/oauth/pedido/", pedido)
            self.assertEqual(resposta.status_code, 400)
            self.assertNotIn("redirecionar", resposta.data)

    def test_pkce_ausente_volta_como_erro_ao_aplicativo(self):
        client_id = self._registrar()["client_id"]

        resposta = self._sessao().get(
            "/api/v1/oauth/pedido/", self._pedido(client_id, "x" * 43, code_challenge_method="plain")
        )

        retorno = parse_qs(urlsplit(resposta.data["redirecionar"]).query)
        self.assertEqual(retorno["error"], ["invalid_request"])
        self.assertEqual(retorno["state"], ["estado-1"])

    def test_negar_devolve_access_denied_sem_criar_conexao(self):
        client_id = self._registrar()["client_id"]
        _, desafio = _pkce()

        resposta = self._sessao().post(
            "/api/v1/oauth/pedido/", {**self._pedido(client_id, desafio), "permitir": False}, format="json"
        )

        self.assertIn("error=access_denied", resposta.data["redirecionar"])
        self.assertFalse(ConexaoOAuth.objects.exists())

    def test_nao_autoriza_escritorio_alheio(self):
        client_id = self._registrar()["client_id"]
        _, desafio = _pkce()
        sem_vinculo = Escritorio.objects.create(nome="Sem vínculo", criado_por=self.ana)

        resposta = self._sessao().post(
            "/api/v1/oauth/pedido/",
            {**self._pedido(client_id, desafio), "permitir": True, "escritorio_id": str(sem_vinculo.pk)},
            format="json",
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(ConexaoOAuth.objects.exists())

    def test_token_de_api_nao_autoriza_aplicativo(self):
        _, texto = criar_token_api(usuario=self.ana, nome="Agente", senha=SENHA)
        client_id = self._registrar()["client_id"]
        _, desafio = _pkce()

        resposta = APIClient()
        resposta.credentials(HTTP_AUTHORIZATION=f"Bearer {texto}")
        self.assertEqual(
            resposta.get("/api/v1/oauth/pedido/", self._pedido(client_id, desafio)).status_code, 401
        )

    # ------------------------------------------------------------ troca de código
    def test_verifier_errado_e_codigo_reusado_sao_recusados(self):
        client_id = self._registrar()["client_id"]
        verificador, desafio = _pkce()
        codigo = self._autorizar(client_id, desafio)["code"][0]

        errado = self._trocar(client_id, codigo, _pkce()[0])
        self.assertEqual(errado.data["error"], "invalid_grant")
        # o código já foi gasto: nem o verifier certo o aproveita, e a conexão cai
        self.assertEqual(self._trocar(client_id, codigo, verificador).data["error"], "invalid_grant")
        self.assertIsNotNone(ConexaoOAuth.objects.get().revogada_em)

    def test_reuso_do_codigo_depois_da_troca_derruba_o_token_emitido(self):
        client_id = self._registrar()["client_id"]
        verificador, desafio = _pkce()
        codigo = self._autorizar(client_id, desafio)["code"][0]
        tokens = self._trocar(client_id, codigo, verificador).data

        self.assertEqual(self._trocar(client_id, codigo, verificador).status_code, 400)
        self.assertEqual(self._api(tokens["access_token"]).status_code, 401)

    def test_codigo_de_outro_aplicativo_nao_serve(self):
        dono = self._registrar()["client_id"]
        intruso = self._registrar()["client_id"]
        verificador, desafio = _pkce()
        codigo = self._autorizar(dono, desafio)["code"][0]

        self.assertEqual(self._trocar(intruso, codigo, verificador).data["error"], "invalid_grant")

    # ------------------------------------------------------------ renovação
    def test_renovacao_gira_e_reuso_tardio_revoga_a_conexao(self):
        client_id, tokens = self._conectar()

        def renovar(refresh):
            return self._form("/oauth/token", {
                "grant_type": "refresh_token", "client_id": client_id, "refresh_token": refresh,
            })

        novos = renovar(tokens["refresh_token"])
        self.assertEqual(novos.status_code, 200)
        self.assertNotEqual(novos.data["refresh_token"], tokens["refresh_token"])

        # reuso imediato (dois pedidos simultâneos do cliente): recusa, mas não revoga
        self.assertEqual(renovar(tokens["refresh_token"]).status_code, 400)
        self.assertEqual(self._api(novos.data["access_token"]).status_code, 200)

        # reuso tardio: sinal de roubo, a conexão inteira cai
        RenovacaoOAuth.objects.filter(usado_em__isnull=False).update(
            usado_em=timezone.now() - timedelta(minutes=5)
        )
        self.assertEqual(renovar(tokens["refresh_token"]).status_code, 400)
        self.assertEqual(self._api(novos.data["access_token"]).status_code, 401)
        self.assertTrue(EventoAuditoria.objects.filter(acao="oauth.reuso_de_renovacao").exists())

    # ------------------------------------------------------------ revogação
    def test_revogar_no_app_corta_o_acesso_na_hora(self):
        _, tokens = self._conectar()
        conexao = ConexaoOAuth.objects.get()

        self.assertEqual(self._sessao().delete(f"/api/v1/auth/conexoes/{conexao.pk}/").status_code, 204)

        self.assertEqual(self._api(tokens["access_token"]).status_code, 401)
        self.assertEqual(self._sessao().get("/api/v1/auth/conexoes/").data, [])
        self.assertTrue(EventoAuditoria.objects.filter(acao="oauth.conexao_revogada").exists())

    def test_revogacao_rfc7009_pelo_aplicativo(self):
        client_id, tokens = self._conectar()

        resposta = self._form("/oauth/revogar", {"client_id": client_id, "token": tokens["refresh_token"]})

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(self._api(tokens["access_token"]).status_code, 401)

    def test_sair_do_escritorio_ou_trocar_a_senha_corta_o_acesso(self):
        _, tokens = self._conectar()
        self.membro.status = MembroEscritorio.Status.SUSPENSO
        self.membro.save()
        self.assertEqual(self._api(tokens["access_token"]).status_code, 401)

        self.membro.status = MembroEscritorio.Status.ATIVO
        self.membro.save()
        self.assertEqual(self._api(tokens["access_token"]).status_code, 200)
        revogar_tokens_api(self.ana)
        self.assertEqual(self._api(tokens["access_token"]).status_code, 401)

    # ------------------------------------------------------------ introspecção e registro
    def test_introspeccao_exige_segredo_e_informa_audiencia_e_escritorio(self):
        _, tokens = self._conectar()
        _, manual = criar_token_api(usuario=self.ana, nome="Agente", senha=SENHA)

        def perguntar(token, segredo=SEGREDO):
            return self._form("/oauth/introspeccao", {"token": token}, HTTP_AUTHORIZATION=f"Bearer {segredo}")

        self.assertEqual(perguntar(tokens["access_token"], "errado").status_code, 401)
        dados = perguntar(tokens["access_token"]).data
        self.assertTrue(dados["active"])
        self.assertEqual(dados["aud"], RECURSO)
        self.assertEqual(dados["escritorio_id"], str(self.escritorio.pk))
        self.assertFalse(perguntar(manual).data["active"])  # token manual não é do conector
        self.assertFalse(perguntar(tokens["refresh_token"]).data["active"])

    def test_registro_recusa_redirect_inseguro(self):
        for uri in ("http://atacante.exemplo.invalid/cb", "javascript:alert(1)", "https://x.invalid/cb#frag"):
            resposta = self.anonimo.post(
                "/oauth/registrar", {"client_name": "X", "redirect_uris": [uri]}, format="json"
            )
            self.assertEqual(resposta.data["error"], "invalid_redirect_uri", uri)
        self._registrar(redirect_uris=["http://localhost:33418/callback"])

    def test_cliente_confidencial_precisa_do_segredo(self):
        registro = self._registrar(token_endpoint_auth_method="client_secret_basic")
        verificador, desafio = _pkce()
        codigo = self._autorizar(registro["client_id"], desafio)["code"][0]

        sem_segredo = self._trocar(registro["client_id"], codigo, verificador)
        self.assertEqual((sem_segredo.status_code, sem_segredo.data["error"]), (401, "invalid_client"))

        verificador, desafio = _pkce()
        codigo = self._autorizar(registro["client_id"], desafio)["code"][0]
        basic = base64.b64encode(f"{registro['client_id']}:{registro['client_secret']}".encode()).decode()
        com_segredo = self._trocar(registro["client_id"], codigo, verificador, HTTP_AUTHORIZATION=f"Basic {basic}")
        self.assertEqual(com_segredo.status_code, 200)

    @override_settings(OAUTH_RECURSOS=[])
    def test_conector_desligado_nao_registra_aplicativos(self):
        resposta = self.anonimo.post(
            "/oauth/registrar", {"client_name": "X", "redirect_uris": [REDIRECT]}, format="json"
        )
        self.assertEqual(resposta.status_code, 503)
