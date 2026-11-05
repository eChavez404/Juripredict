import os
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from accounts.models import TokenApi
from accounts.services import confirmar_reset_senha, excluir_conta
from accounts.tokens_api import criar_token_api
from api.models import Cliente, DocumentoProcesso, Processo
from auditlog.models import EventoAuditoria
from organizations.models import Escritorio, MembroEscritorio

User = get_user_model()
SENHA = "uma-senha-bem-forte-123"
MEDIA = tempfile.mkdtemp(prefix="juripredict-test-media-")


class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="ana@x.com", email="ana@x.com", password=SENHA)
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=self.user)
        MembroEscritorio.objects.create(escritorio=self.escritorio, usuario=self.user, papel="OWNER")
        self.cliente = Cliente.objects.create(
            escritorio=self.escritorio, usuario=self.user, nome="Cliente", cpf_cnpj="x"
        )
        self.processo = self._processo(self.escritorio, self.cliente, self.user, "0000001")
        self.escritorio_id = str(self.escritorio.pk)

    def _processo(self, escritorio, cliente, usuario, numero):
        return Processo.objects.create(
            escritorio=escritorio, usuario=usuario, cliente=cliente,
            numero_cnj=f"{numero}-00.2024.5.16.0001", vara="V", comarca="C", parte_contraria="X",
        )

    def novo_token(self, **extra):
        token, texto = criar_token_api(usuario=self.user, nome="Agente", senha=SENHA, **extra)
        return token, texto

    def com_token(self, texto, escritorio=True):
        cliente = APIClient()
        extra = {"HTTP_AUTHORIZATION": f"Bearer {texto}"}
        if escritorio:
            extra["HTTP_X_ESCRITORIO_ID"] = self.escritorio_id
        cliente.credentials(**extra)
        return cliente

    def com_sessao(self, usuario=None):
        cliente = APIClient()
        cliente.force_authenticate(usuario or self.user)
        return cliente


class CicloDeVidaTests(Base):
    def test_cria_com_a_senha_e_devolve_o_texto_uma_unica_vez(self):
        sessao = self.com_sessao()

        criado = sessao.post(
            reverse("tokens-api"), {"nome": "Meu agente", "senha": SENHA}, format="json"
        )

        self.assertEqual(criado.status_code, 201)
        texto = criado.data["token"]
        self.assertTrue(texto.startswith("jp_"))
        self.assertEqual(criado.data["prefixo"], texto[:10])
        lista = sessao.get(reverse("tokens-api")).data
        self.assertEqual(len(lista), 1)
        for campo in ("token", "hash"):
            self.assertNotIn(campo, lista[0])
        # só o hash fica no banco, nunca o texto
        guardado = TokenApi.objects.get()
        self.assertNotEqual(guardado.hash, texto)
        self.assertNotIn(texto, guardado.hash)

    def test_senha_errada_nao_cria(self):
        resposta = self.com_sessao().post(
            reverse("tokens-api"), {"nome": "x", "senha": "errada"}, format="json"
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(TokenApi.objects.exists())

    def test_validade_padrao_e_personalizada(self):
        padrao, _ = self.novo_token()
        curto, _ = self.novo_token(validade_dias=7)

        self.assertAlmostEqual((padrao.expira_em - timezone.now()).days, 89, delta=1)
        self.assertAlmostEqual((curto.expira_em - timezone.now()).days, 6, delta=1)

    def test_validade_fora_do_intervalo_e_recusada(self):
        for dias in (0, 366):
            with self.subTest(dias=dias):
                r = self.com_sessao().post(
                    reverse("tokens-api"), {"nome": "x", "senha": SENHA, "validade_dias": dias}, format="json"
                )
                self.assertEqual(r.status_code, 400)

    @override_settings(API_TOKEN_MAX_ATIVOS=2)
    def test_limite_de_tokens_ativos_e_revogar_libera_vaga(self):
        primeiro, _ = self.novo_token()
        self.novo_token()
        sessao = self.com_sessao()

        recusado = sessao.post(reverse("tokens-api"), {"nome": "3", "senha": SENHA}, format="json")
        sessao.delete(reverse("token-api-detalhe", args=[primeiro.pk]))
        liberado = sessao.post(reverse("tokens-api"), {"nome": "3", "senha": SENHA}, format="json")

        self.assertEqual(recusado.status_code, 400)
        self.assertEqual(liberado.status_code, 201)

    def test_revogar_e_idempotente_e_so_vale_para_o_dono(self):
        token, texto = self.novo_token()
        outro = User.objects.create_user(username="o@x.com", email="o@x.com", password="x")

        alheio = self.com_sessao(outro).delete(reverse("token-api-detalhe", args=[token.pk]))
        proprio = self.com_sessao().delete(reverse("token-api-detalhe", args=[token.pk]))
        de_novo = self.com_sessao().delete(reverse("token-api-detalhe", args=[token.pk]))

        self.assertEqual(alheio.status_code, 400)
        self.assertEqual((proprio.status_code, de_novo.status_code), (204, 204))
        self.assertEqual(self.com_token(texto).get("/api/v1/processos/").status_code, 401)

    def test_lista_so_mostra_os_tokens_da_propria_pessoa(self):
        self.novo_token()
        outro = User.objects.create_user(username="o@x.com", email="o@x.com", password="x")

        self.assertEqual(self.com_sessao(outro).get(reverse("tokens-api")).data, [])

    def test_criar_e_revogar_entram_na_auditoria_de_cada_escritorio_sem_o_texto_do_token(self):
        segundo = Escritorio.objects.create(nome="Outra banca", criado_por=self.user)
        MembroEscritorio.objects.create(escritorio=segundo, usuario=self.user, papel="ADVOGADO")
        token, texto = self.novo_token()

        self.com_sessao().delete(reverse("token-api-detalhe", args=[token.pk]))

        for escritorio in (self.escritorio, segundo):
            acoes = set(EventoAuditoria.objects.filter(escritorio=escritorio).values_list("acao", flat=True))
            self.assertEqual(acoes, {"token_api.criado", "token_api.revogado"})
        evento = EventoAuditoria.objects.filter(acao="token_api.criado").first()
        self.assertEqual(evento.alteracoes["nome"], "Agente")
        self.assertEqual(evento.alteracoes["credencial"], texto[:10])
        self.assertNotIn(texto, str(list(EventoAuditoria.objects.values_list("alteracoes", flat=True))))


class AcessoPorTokenTests(Base):
    def test_le_rotas_permitidas_com_o_escritorio_do_usuario(self):
        _, texto = self.novo_token()
        agente = self.com_token(texto)

        for caminho in ("/api/v1/processos/", f"/api/v1/processos/{self.processo.pk}/",
                        f"/api/v1/processos/{self.processo.pk}/andamentos/",
                        f"/api/v1/processos/{self.processo.pk}/documentos/",
                        "/api/v1/eventos/", "/api/v1/jurimetria/", "/api/v1/dashboard/"):
            with self.subTest(caminho=caminho):
                self.assertEqual(agente.get(caminho).status_code, 200)
        self.assertEqual(self.com_token(texto, escritorio=False).get("/api/v1/auth/me/").status_code, 200)

    def test_nao_escreve_nem_altera_nada(self):
        _, texto = self.novo_token()
        agente = self.com_token(texto)
        url = f"/api/v1/processos/{self.processo.pk}/"

        respostas = [
            agente.post("/api/v1/processos/", {}, format="json"),
            agente.patch(url, {"titulo": "x"}, format="json"),
            agente.put(url, {}, format="json"),
            agente.delete(url),
            agente.post(f"{url}andamentos/sincronizar/"),
            agente.post(f"{url}documentos/", {}, format="multipart"),
            agente.patch("/api/v1/auth/me/", {"nome": "x"}, format="json"),
        ]

        self.assertEqual({r.status_code for r in respostas}, {403})
        self.assertTrue(Processo.objects.filter(pk=self.processo.pk, titulo="").exists())

    def test_rotas_sensiveis_ficam_fora_mesmo_para_leitura(self):
        _, texto = self.novo_token()
        agente = self.com_token(texto)

        for caminho in ("/api/v1/clientes/", "/api/v1/auditoria/", "/api/v1/auth/me/exportar/",
                        f"/api/v1/escritorios/{self.escritorio_id}/membros/"):
            with self.subTest(caminho=caminho):
                self.assertEqual(agente.get(caminho).status_code, 403)

    def test_token_nao_gerencia_tokens(self):
        token, texto = self.novo_token()
        agente = self.com_token(texto)

        criar = agente.post(reverse("tokens-api"), {"nome": "x", "senha": SENHA}, format="json")

        listar = agente.get(reverse("tokens-api"))
        revogar = agente.delete(reverse("token-api-detalhe", args=[token.pk]))

        # nessas rotas só a sessão de pessoa (JWT) é aceita: o token nem é reconhecido
        self.assertEqual({criar.status_code, listar.status_code, revogar.status_code}, {401})
        self.assertEqual(TokenApi.objects.count(), 1)
        self.assertIsNone(TokenApi.objects.get(pk=token.pk).revogado_em)

    def test_token_invalido_expirado_revogado_ou_de_conta_inativa_e_401(self):
        token, texto = self.novo_token()
        expirado, texto_exp = self.novo_token()
        TokenApi.objects.filter(pk=expirado.pk).update(expira_em=timezone.now() - timedelta(seconds=1))

        casos = {"inventado": "jp_" + "x" * 40, "expirado": texto_exp}
        for nome, valor in casos.items():
            with self.subTest(caso=nome):
                self.assertEqual(self.com_token(valor).get("/api/v1/processos/").status_code, 401)

        self.user.is_active = False
        self.user.save(update_fields=("is_active",))
        self.assertEqual(self.com_token(texto).get("/api/v1/processos/").status_code, 401)

    def test_jwt_continua_funcionando_e_nao_e_confundido_com_token(self):
        self.assertEqual(self.com_sessao().get("/api/v1/processos/", HTTP_X_ESCRITORIO_ID=self.escritorio_id).status_code, 200)

    def test_nao_ve_processo_de_outro_escritorio(self):
        outro = User.objects.create_user(username="o@x.com", email="o@x.com", password="x")
        esc2 = Escritorio.objects.create(nome="Outra", criado_por=outro)
        MembroEscritorio.objects.create(escritorio=esc2, usuario=outro, papel="OWNER")
        cli2 = Cliente.objects.create(escritorio=esc2, usuario=outro, nome="C2", cpf_cnpj="y")
        alheio = self._processo(esc2, cli2, outro, "0000002")
        _, texto = self.novo_token()
        agente = self.com_token(texto)

        direto = agente.get(f"/api/v1/processos/{alheio.pk}/andamentos/")
        lista = agente.get("/api/v1/processos/").data

        self.assertEqual(direto.status_code, 404)
        self.assertEqual([p["id"] for p in lista], [self.processo.pk])
        # tentar o escritório alheio no cabeçalho também não funciona
        forjado = self.com_token(texto)
        forjado.credentials(HTTP_AUTHORIZATION=f"Bearer {texto}", HTTP_X_ESCRITORIO_ID=str(esc2.pk))
        with self.assertLogs("accounts.middleware", level="WARNING"):
            self.assertEqual(forjado.get("/api/v1/processos/").status_code, 403)
        # e o log do escritório alheio não pode receber evento de quem não é membro
        self.assertFalse(EventoAuditoria.objects.filter(escritorio=esc2).exists())

    @override_settings(MEDIA_ROOT=MEDIA)
    def test_links_assinados_de_arquivo_nao_chegam_ao_token_mas_chegam_a_pessoa(self):
        self.processo.arquivo_peticao_inicial = SimpleUploadedFile("p.pdf", b"%PDF-1")
        self.processo.save()
        DocumentoProcesso.objects.create(
            processo=self.processo, arquivo=SimpleUploadedFile("d.pdf", b"%PDF-1"), nome="d.pdf", tamanho=6
        )
        _, texto = self.novo_token()
        agente = self.com_token(texto)
        sessao = self.com_sessao()
        cab = {"HTTP_X_ESCRITORIO_ID": self.escritorio_id}

        self.assertIsNone(agente.get("/api/v1/processos/").data[0]["arquivo_peticao_inicial_url"])
        self.assertIsNone(agente.get(f"/api/v1/processos/{self.processo.pk}/").data["arquivo_peticao_inicial_url"])
        self.assertIsNone(agente.get(f"/api/v1/processos/{self.processo.pk}/documentos/").data[0]["url"])
        self.assertTrue(sessao.get("/api/v1/processos/", **cab).data[0]["arquivo_peticao_inicial_url"])
        self.assertTrue(sessao.get(f"/api/v1/processos/{self.processo.pk}/documentos/", **cab).data[0]["url"])

    def test_ultimo_uso_e_gravado_e_nao_a_cada_requisicao(self):
        token, texto = self.novo_token()
        agente = self.com_token(texto)

        agente.get("/api/v1/processos/")
        primeiro = TokenApi.objects.get(pk=token.pk).ultimo_uso_em
        agente.get("/api/v1/processos/")
        segundo = TokenApi.objects.get(pk=token.pk).ultimo_uso_em

        self.assertIsNotNone(primeiro)
        self.assertEqual(primeiro, segundo)


class AuditoriaDeAcessoTests(Base):
    def _eventos(self, acao):
        return EventoAuditoria.objects.filter(acao=acao)

    def test_cada_leitura_vira_evento_com_credencial_e_so_os_nomes_dos_filtros(self):
        token, texto = self.novo_token()

        self.com_token(texto).get(f"/api/v1/processos/?q=SEGREDO-DO-CLIENTE&status=ATIVO")
        self.com_token(texto).get(f"/api/v1/processos/{self.processo.pk}/andamentos/")

        lista, andamentos = list(self._eventos("token_api.leitura").order_by("criado_em"))
        self.assertEqual((lista.recurso_tipo, lista.recurso_id), ("processo", "lista"))
        self.assertEqual(lista.alteracoes["filtros"], ["q", "status"])
        self.assertNotIn("SEGREDO-DO-CLIENTE", str(lista.alteracoes))
        self.assertEqual(lista.alteracoes["credencial"], texto[:10])
        self.assertEqual(lista.alteracoes["status"], 200)
        self.assertEqual((andamentos.recurso_id, andamentos.alteracoes["subrecurso"]),
                         (str(self.processo.pk), "andamentos"))
        self.assertEqual(lista.ator, self.user)
        self.assertEqual(lista.escritorio, self.escritorio)

    def test_tentativa_bloqueada_tambem_e_auditada(self):
        _, texto = self.novo_token()
        agente = self.com_token(texto)

        agente.get("/api/v1/clientes/")
        agente.delete(f"/api/v1/processos/{self.processo.pk}/")

        negados = list(self._eventos("token_api.negado").order_by("criado_em"))
        self.assertEqual([(e.recurso_tipo, e.alteracoes["metodo"], e.alteracoes["status"]) for e in negados],
                         [("clientes", "GET", 403), ("processo", "DELETE", 403)])
        self.assertTrue(Processo.objects.filter(pk=self.processo.pk).exists())

    def test_sondagem_de_processo_alheio_fica_registrada_como_negada(self):
        _, texto = self.novo_token()

        self.com_token(texto).get("/api/v1/processos/999999/andamentos/")

        evento = self._eventos("token_api.negado").get()
        self.assertEqual(evento.alteracoes["status"], 404)

    def test_pessoa_com_sessao_normal_nao_gera_evento_de_token(self):
        self.com_sessao().get("/api/v1/processos/", HTTP_X_ESCRITORIO_ID=self.escritorio_id)

        self.assertFalse(EventoAuditoria.objects.filter(acao__startswith="token_api.leitura").exists())

    def test_consulta_de_sessao_para_achar_o_escritorio_nao_polui_o_log(self):
        _, texto = self.novo_token()

        self.com_token(texto, escritorio=False).get("/api/v1/auth/me/")
        self.com_token(texto).get("/api/v1/auth/me/")  # mesmo com escritório informado

        self.assertFalse(self._eventos("token_api.leitura").exists())

    def test_sem_escritorio_valido_nao_grava_evento_mas_deixa_aviso_no_log(self):
        _, texto = self.novo_token()
        agente = self.com_token(texto, escritorio=False)

        with self.assertLogs("accounts.middleware", level="WARNING") as log:
            agente.get("/api/v1/clientes/")

        self.assertIn("acesso negado sem escritório válido", log.output[0])
        self.assertFalse(EventoAuditoria.objects.filter(acao="token_api.negado").exists())

    def test_falha_ao_auditar_nao_derruba_a_resposta(self):
        _, texto = self.novo_token()

        with mock.patch("accounts.middleware.registrar_evento_auditoria", side_effect=RuntimeError):
            with self.assertLogs("accounts.middleware", level="ERROR"):
                resposta = self.com_token(texto).get("/api/v1/processos/")

        self.assertEqual(resposta.status_code, 200)

    def test_administrador_enxerga_os_eventos_pela_api_de_auditoria(self):
        _, texto = self.novo_token()
        self.com_token(texto).get("/api/v1/processos/")

        resposta = self.com_sessao().get("/api/v1/auditoria/", HTTP_X_ESCRITORIO_ID=self.escritorio_id)

        eventos = resposta.data["results"] if isinstance(resposta.data, dict) else resposta.data
        self.assertIn("token_api.leitura", [e["acao"] for e in eventos])


class RevogacaoAutomaticaTests(Base):
    def test_redefinir_a_senha_revoga_os_tokens_de_api(self):
        token, texto = self.novo_token()
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        confirmar_reset_senha(uid=uid, token=default_token_generator.make_token(self.user), nova_senha="outra-senha-forte-456")

        self.assertIsNotNone(TokenApi.objects.get(pk=token.pk).revogado_em)
        self.assertEqual(self.com_token(texto).get("/api/v1/processos/").status_code, 401)

    def test_excluir_a_conta_revoga_os_tokens_de_api(self):
        token, texto = self.novo_token()
        # único membro do escritório: a exclusão é permitida e desativa o escritório solo
        excluir_conta(usuario=self.user, senha=SENHA)

        self.assertIsNotNone(TokenApi.objects.get(pk=token.pk).revogado_em)
        self.assertEqual(self.com_token(texto).get("/api/v1/processos/").status_code, 401)
