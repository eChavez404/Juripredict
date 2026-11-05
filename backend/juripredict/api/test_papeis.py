from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from accounts.tokens_api import criar_token_api
from organizations.capabilities import (
    CAPABILITIES_POR_PAPEL,
    capabilities_do_membro,
)
from organizations.models import Escritorio, MembroEscritorio

from .crypto_utils import decrypt_data
from .models import Cliente, Processo
from .serializers import mascarar_documento

User = get_user_model()
SENHA = "uma-senha-bem-forte-123"
NOVAS = {
    "processos.valores.ler", "jurimetria.ler", "clientes.documento.ler",
    "processos.excluir", "clientes.excluir",
}
PAPEL = MembroEscritorio.Papel


class TabelaDePapeisTests(SimpleTestCase):
    def test_estagiario_nao_tem_nenhuma_das_capabilities_restritas(self):
        self.assertEqual(CAPABILITIES_POR_PAPEL[PAPEL.ESTAGIARIO] & NOVAS, set())

    def test_advogado_admin_e_proprietario_tem_todas(self):
        for papel in (PAPEL.ADVOGADO, PAPEL.ADMIN, PAPEL.OWNER):
            with self.subTest(papel=papel):
                self.assertLessEqual(NOVAS, CAPABILITIES_POR_PAPEL[papel])

    def test_so_gestores_gerenciam_equipe_e_veem_auditoria(self):
        for papel in (PAPEL.ADVOGADO, PAPEL.ESTAGIARIO):
            self.assertFalse({"membros.gerenciar", "auditoria.ler"} & CAPABILITIES_POR_PAPEL[papel])

    def test_membro_suspenso_ou_ausente_nao_tem_capability_alguma(self):
        suspenso = MembroEscritorio(papel=PAPEL.OWNER, status=MembroEscritorio.Status.SUSPENSO)

        self.assertEqual(capabilities_do_membro(suspenso), [])
        self.assertEqual(capabilities_do_membro(None), [])


class MascaraTests(SimpleTestCase):
    def test_mantem_so_os_dois_ultimos_digitos_e_a_pontuacao(self):
        self.assertEqual(mascarar_documento("123.456.789-09"), "***.***.***-09")
        self.assertEqual(mascarar_documento("12345678909"), "*********09")
        self.assertEqual(mascarar_documento("12.345.678/0001-95"), "**.***.***/****-95")

    def test_valor_curto_ou_vazio_nao_quebra(self):
        self.assertEqual(mascarar_documento(""), "")
        self.assertEqual(mascarar_documento("7"), "7")


class PapeisBase(TestCase):
    def setUp(self):
        cache.clear()
        dono = User.objects.create_user(username="dono@x.com", email="dono@x.com", password=SENHA)
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=dono)
        self.usuarios = {}
        for papel in PAPEL.values:
            usuario = User.objects.create_user(
                username=f"{papel.lower()}@x.com", email=f"{papel.lower()}@x.com", password=SENHA
            )
            MembroEscritorio.objects.create(escritorio=self.escritorio, usuario=usuario, papel=papel)
            self.usuarios[papel] = usuario
        self.cliente = Cliente.objects.create(
            escritorio=self.escritorio, usuario=dono, nome="Cliente", cpf_cnpj="",
        )
        from .crypto_utils import encrypt_data, hash_data

        self.cliente.cpf_cnpj = encrypt_data("12345678909")
        self.cliente.cpf_cnpj_hash = hash_data("12345678909")
        self.cliente.save()
        self.processo = Processo.objects.create(
            escritorio=self.escritorio, usuario=dono, cliente=self.cliente,
            numero_cnj="0000001-00.2024.5.16.0001", vara="V", comarca="C",
            parte_contraria="X", valor_causa=Decimal("12345.67"),
        )

    def como(self, papel):
        cliente = APIClient()
        cliente.force_authenticate(self.usuarios[papel])
        cliente.credentials(HTTP_X_ESCRITORIO_ID=str(self.escritorio.pk))
        return cliente

    def com_token(self, papel):
        _, texto = criar_token_api(usuario=self.usuarios[papel], nome="a", senha=SENHA)
        cliente = APIClient()
        cliente.credentials(
            HTTP_AUTHORIZATION=f"Bearer {texto}", HTTP_X_ESCRITORIO_ID=str(self.escritorio.pk)
        )
        return cliente


class ValorDaCausaTests(PapeisBase):
    def test_quem_tem_a_capability_ve_o_valor(self):
        for papel in (PAPEL.ADVOGADO, PAPEL.ADMIN, PAPEL.OWNER):
            with self.subTest(papel=papel):
                dados = self.como(papel).get(f"/api/v1/processos/{self.processo.pk}/").data
                self.assertEqual(Decimal(dados["valor_causa"]), Decimal("12345.67"))

    def test_estagiario_recebe_o_valor_nulo_no_detalhe_e_na_lista(self):
        agente = self.como(PAPEL.ESTAGIARIO)

        detalhe = agente.get(f"/api/v1/processos/{self.processo.pk}/").data
        lista = agente.get("/api/v1/processos/").data

        self.assertIsNone(detalhe["valor_causa"])
        self.assertIsNone(lista[0]["valor_causa"])
        self.assertNotIn("12345", str(detalhe) + str(lista))

    def test_estagiario_salvar_o_formulario_nao_apaga_nem_altera_o_valor(self):
        agente = self.como(PAPEL.ESTAGIARIO)

        agente.patch(f"/api/v1/processos/{self.processo.pk}/", {"titulo": "Novo título", "valor_causa": "1.00"}, format="json")
        # o formulário do estagiário devolve o valor nulo: também não pode zerar
        agente.patch(f"/api/v1/processos/{self.processo.pk}/", {"valor_causa": None}, format="json")

        self.processo.refresh_from_db()
        self.assertEqual(self.processo.titulo, "Novo título")
        self.assertEqual(self.processo.valor_causa, Decimal("12345.67"))

    def test_formulario_multipart_do_estagiario_com_valor_vazio_salva_sem_erro_e_sem_zerar(self):
        # é assim que o frontend envia: FormData, com o campo escondido vazio
        resposta = self.como(PAPEL.ESTAGIARIO).patch(
            f"/api/v1/processos/{self.processo.pk}/",
            {"titulo": "Via formulário", "valor_causa": ""},
            format="multipart",
        )

        self.assertEqual(resposta.status_code, 200)
        self.processo.refresh_from_db()
        self.assertEqual(self.processo.titulo, "Via formulário")
        self.assertEqual(self.processo.valor_causa, Decimal("12345.67"))

    def test_estagiario_cria_processo_sem_conseguir_gravar_valor(self):
        resposta = self.como(PAPEL.ESTAGIARIO).post("/api/v1/processos/", {
            "numero_cnj": "0000009-00.2024.5.16.0001", "cliente": self.cliente.pk, "vara": "V",
            "comarca": "C", "parte_contraria": "X", "valor_causa": "999.00",
        }, format="json")

        self.assertEqual(resposta.status_code, 201)
        self.assertIsNone(Processo.objects.get(pk=resposta.data["id"]).valor_causa)

    def test_advogado_continua_editando_o_valor(self):
        self.como(PAPEL.ADVOGADO).patch(f"/api/v1/processos/{self.processo.pk}/", {"valor_causa": "50.00"}, format="json")

        self.processo.refresh_from_db()
        self.assertEqual(self.processo.valor_causa, Decimal("50.00"))

    def test_o_token_do_estagiario_herda_a_restricao(self):
        agente = self.com_token(PAPEL.ESTAGIARIO)

        self.assertIsNone(agente.get(f"/api/v1/processos/{self.processo.pk}/").data["valor_causa"])
        self.assertIsNone(agente.get("/api/v1/processos/").data[0]["valor_causa"])

    def test_o_token_do_advogado_ve_o_valor(self):
        agente = self.com_token(PAPEL.ADVOGADO)

        self.assertEqual(Decimal(agente.get("/api/v1/processos/").data[0]["valor_causa"]), Decimal("12345.67"))


class JurimetriaPorPapelTests(PapeisBase):
    def test_estagiario_recebe_403_e_os_demais_200(self):
        self.assertEqual(self.como(PAPEL.ESTAGIARIO).get("/api/v1/jurimetria/").status_code, 403)
        for papel in (PAPEL.ADVOGADO, PAPEL.ADMIN, PAPEL.OWNER):
            with self.subTest(papel=papel):
                self.assertEqual(self.como(papel).get("/api/v1/jurimetria/").status_code, 200)

    def test_vale_tambem_para_o_token(self):
        self.assertEqual(self.com_token(PAPEL.ESTAGIARIO).get("/api/v1/jurimetria/").status_code, 403)
        self.assertEqual(self.com_token(PAPEL.ADVOGADO).get("/api/v1/jurimetria/").status_code, 200)


class ExclusaoPorPapelTests(PapeisBase):
    def test_estagiario_nao_exclui_processo_nem_cliente(self):
        agente = self.como(PAPEL.ESTAGIARIO)

        r1 = agente.delete(f"/api/v1/processos/{self.processo.pk}/")
        r2 = agente.delete(f"/api/v1/clientes/{self.cliente.pk}/")

        self.assertEqual((r1.status_code, r2.status_code), (403, 403))
        self.assertTrue(Processo.objects.filter(pk=self.processo.pk).exists())
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())

    def test_advogado_exclui_processo_e_cliente(self):
        agente = self.como(PAPEL.ADVOGADO)

        self.assertEqual(agente.delete(f"/api/v1/processos/{self.processo.pk}/").status_code, 204)
        self.assertEqual(agente.delete(f"/api/v1/clientes/{self.cliente.pk}/").status_code, 204)

    def test_estagiario_continua_criando_e_editando(self):
        agente = self.como(PAPEL.ESTAGIARIO)

        edicao = agente.patch(f"/api/v1/processos/{self.processo.pk}/", {"titulo": "x"}, format="json")
        cliente = agente.post("/api/v1/clientes/", {"nome": "Novo", "cpf_cnpj": "987.654.321-00"}, format="json")

        self.assertEqual(edicao.status_code, 200)
        self.assertEqual(cliente.status_code, 201)


class DocumentoDoClientePorPapelTests(PapeisBase):
    def test_estagiario_ve_o_documento_mascarado_e_os_demais_completo(self):
        mascarado = self.como(PAPEL.ESTAGIARIO).get(f"/api/v1/clientes/{self.cliente.pk}/").data["cpf_cnpj"]
        lista = self.como(PAPEL.ESTAGIARIO).get("/api/v1/clientes/").data[0]["cpf_cnpj"]

        self.assertEqual((mascarado, lista), ("*********09", "*********09"))
        for papel in (PAPEL.ADVOGADO, PAPEL.ADMIN, PAPEL.OWNER):
            with self.subTest(papel=papel):
                completo = self.como(papel).get(f"/api/v1/clientes/{self.cliente.pk}/").data["cpf_cnpj"]
                self.assertEqual(completo, "12345678909")

    def test_estagiario_edita_o_cliente_sem_alterar_nem_corromper_o_documento(self):
        agente = self.como(PAPEL.ESTAGIARIO)

        # o formulário devolve o valor mascarado que recebeu
        agente.put(f"/api/v1/clientes/{self.cliente.pk}/", {"nome": "Renomeado", "cpf_cnpj": "*********09"}, format="json")
        agente.patch(f"/api/v1/clientes/{self.cliente.pk}/", {"cpf_cnpj": "000.000.000-00"}, format="json")

        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nome, "Renomeado")
        self.assertEqual(decrypt_data(self.cliente.cpf_cnpj), "12345678909")

    def test_advogado_continua_alterando_o_documento(self):
        self.como(PAPEL.ADVOGADO).patch(f"/api/v1/clientes/{self.cliente.pk}/", {"cpf_cnpj": "111.222.333-44"}, format="json")

        self.cliente.refresh_from_db()
        self.assertEqual(decrypt_data(self.cliente.cpf_cnpj), "11122233344")


class CapabilitiesNaSessaoTests(PapeisBase):
    def test_a_sessao_expoe_as_capabilities_do_papel_para_o_frontend(self):
        estagiario = self.como(PAPEL.ESTAGIARIO).get("/api/v1/auth/me/").data["capabilities"]
        advogado = self.como(PAPEL.ADVOGADO).get("/api/v1/auth/me/").data["capabilities"]

        self.assertEqual(set(estagiario) & NOVAS, set())
        self.assertLessEqual(NOVAS, set(advogado))
