import io
import json
from datetime import timezone as dt_timezone
from unittest import mock
from urllib import error

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from organizations.models import Escritorio, MembroEscritorio

from .andamentos import sincronizar_processo, sincronizar_todos
from .datajud import (
    DatajudErro,
    DatajudNaoConfigurado,
    TribunalNaoSuportado,
    alias_do_tribunal,
    consultar_movimentos,
)
from .models import Andamento, Cliente, Processo

CNJ_TRT16 = "0001234-56.2023.5.16.0001"


class _Resposta:
    def __init__(self, corpo):
        self._corpo = json.dumps(corpo).encode()

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _hit(*movimentos):
    return {"hits": {"hits": [{"_source": {"movimentos": list(movimentos)}}]}}


class AliasDoTribunalTests(SimpleTestCase):
    def test_trt_e_trf_saem_do_proprio_cnj(self):
        self.assertEqual(alias_do_tribunal(CNJ_TRT16), "trt16")
        self.assertEqual(alias_do_tribunal("0001234-56.2023.5.02.0001"), "trt2")
        self.assertEqual(alias_do_tribunal("00012345620234010001"), "trf1")

    def test_outros_ramos_e_numeros_invalidos_sao_recusados(self):
        for numero in ("0001234-56.2023.8.10.0001", "123", "", "0001234-56.2023.5.00.0001"):
            with self.subTest(numero=numero):
                with self.assertRaises(TribunalNaoSuportado):
                    alias_do_tribunal(numero)


@override_settings(DATAJUD_API_KEY="segredo123")
class ConsultarMovimentosTests(SimpleTestCase):
    def test_monta_a_requisicao_e_le_os_movimentos(self):
        abrir = mock.Mock(return_value=_Resposta(_hit(
            {
                "codigo": 26, "nome": "Distribuição", "dataHora": "2023-05-10T14:30:00.000Z",
                "complementosTabelados": [{"nome": "tipo", "descricao": "sorteio"}],
            },
        )))

        movimentos = consultar_movimentos(CNJ_TRT16, abrir=abrir)

        requisicao = abrir.call_args.args[0]
        self.assertTrue(requisicao.full_url.endswith("/api_publica_trt16/_search"))
        self.assertEqual(requisicao.get_header("Authorization"), "APIKey segredo123")
        self.assertEqual(
            json.loads(requisicao.data)["query"]["match"]["numeroProcesso"], "00012345620235160001"
        )
        self.assertEqual(movimentos, [{
            "data_hora": timezone.datetime(2023, 5, 10, 14, 30, tzinfo=dt_timezone.utc),
            "codigo": 26, "nome": "Distribuição", "complemento": "tipo: sorteio",
        }])

    def test_junta_os_movimentos_de_todos_os_graus(self):
        # o mesmo número aparece uma vez por grau (G1 e G2): pedir só um perderia o outro
        grau1 = {"codigo": 1, "nome": "Sentença", "dataHora": "2023-05-10T10:00:00Z"}
        grau2 = {"codigo": 2, "nome": "Acórdão", "dataHora": "2024-01-10T10:00:00Z"}
        abrir = mock.Mock(return_value=_Resposta({"hits": {"hits": [
            {"_source": {"movimentos": [grau1]}}, {"_source": {"movimentos": [grau2]}},
        ]}}))

        movimentos = consultar_movimentos(CNJ_TRT16, abrir=abrir)

        self.assertEqual([m["nome"] for m in movimentos], ["Sentença", "Acórdão"])
        self.assertGreaterEqual(json.loads(abrir.call_args.args[0].data)["size"], 2)

    @override_settings(DATAJUD_API_KEY="APIKey ja-com-prefixo")
    def test_nao_duplica_o_prefixo_da_chave(self):
        abrir = mock.Mock(return_value=_Resposta(_hit()))

        consultar_movimentos(CNJ_TRT16, abrir=abrir)

        self.assertEqual(abrir.call_args.args[0].get_header("Authorization"), "APIKey ja-com-prefixo")

    def test_data_sem_fuso_e_tratada_como_utc_e_item_incompleto_e_ignorado(self):
        abrir = mock.Mock(return_value=_Resposta(_hit(
            {"codigo": 1, "nome": "Juntada", "dataHora": "2023-05-10T14:30:00"},
            {"codigo": 2, "nome": "", "dataHora": "2023-05-10T14:30:00"},
            {"codigo": 3, "nome": "Sem data", "dataHora": "lixo"},
            {"codigo": 4, "nome": "Impossível", "dataHora": "2023-02-31T10:00:00"},
        )))

        movimentos = consultar_movimentos(CNJ_TRT16, abrir=abrir)

        self.assertEqual(len(movimentos), 1)
        self.assertIsNotNone(movimentos[0]["data_hora"].tzinfo)

    def test_processo_desconhecido_devolve_lista_vazia(self):
        abrir = mock.Mock(return_value=_Resposta({"hits": {"hits": []}}))

        self.assertEqual(consultar_movimentos(CNJ_TRT16, abrir=abrir), [])

    def test_falha_de_rede_vira_erro_sem_vazar_a_chave(self):
        abrir = mock.Mock(side_effect=error.URLError("falhou em api_publica com segredo123"))

        with self.assertRaises(DatajudErro) as contexto:
            consultar_movimentos(CNJ_TRT16, abrir=abrir)

        self.assertNotIn("segredo123", str(contexto.exception))

    def test_resposta_que_nao_e_json_vira_erro(self):
        resposta = _Resposta({})
        resposta.read = lambda: b"<html>"

        with self.assertRaises(DatajudErro):
            consultar_movimentos(CNJ_TRT16, abrir=mock.Mock(return_value=resposta))

    @override_settings(DATAJUD_API_KEY="")
    def test_sem_chave_nao_chama_a_rede(self):
        abrir = mock.Mock()

        with self.assertRaises(DatajudNaoConfigurado):
            consultar_movimentos(CNJ_TRT16, abrir=abrir)

        abrir.assert_not_called()

    def test_tribunal_nao_suportado_nao_chama_a_rede(self):
        abrir = mock.Mock()

        with self.assertRaises(TribunalNaoSuportado):
            consultar_movimentos("0001234-56.2023.8.10.0001", abrir=abrir)

        abrir.assert_not_called()


class AndamentosBase(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(username="a", email="a@x.com", password="x")
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=self.user)
        MembroEscritorio.objects.create(escritorio=self.escritorio, usuario=self.user, papel="OWNER")
        self.cliente = Cliente.objects.create(
            escritorio=self.escritorio, usuario=self.user, nome="C", cpf_cnpj="x"
        )
        self.contador = 0

    def processo(self, escritorio=None, cliente=None, **extra):
        self.contador += 1
        dados = dict(
            escritorio=escritorio or self.escritorio,
            usuario=self.user,
            cliente=cliente or self.cliente,
            numero_cnj=f"{self.contador:07d}-00.2024.5.16.0001",
            vara="V", comarca="C", parte_contraria="X",
        )
        dados.update(extra)
        return Processo.objects.create(**dados)


def _movimentos(*nomes):
    return [
        {"data_hora": timezone.datetime(2024, 1, i + 1, tzinfo=dt_timezone.utc),
         "codigo": i, "nome": nome, "complemento": ""}
        for i, nome in enumerate(nomes)
    ]


class SincronizarProcessoTests(AndamentosBase):
    def test_grava_marca_a_leitura_e_nao_duplica_na_segunda_vez(self):
        processo = self.processo()
        buscar = mock.Mock(return_value=_movimentos("Distribuição", "Audiência"))

        primeira = sincronizar_processo(processo, buscar=buscar)
        segunda = sincronizar_processo(processo, buscar=buscar)

        self.assertEqual((primeira, segunda), (2, 0))
        self.assertEqual(processo.andamentos.count(), 2)
        processo.refresh_from_db()
        self.assertIsNotNone(processo.andamentos_sincronizados_em)

    def test_so_o_movimento_novo_conta_na_segunda_leitura(self):
        processo = self.processo()
        sincronizar_processo(processo, buscar=lambda _: _movimentos("A"))

        novos = sincronizar_processo(processo, buscar=lambda _: _movimentos("A", "B"))

        self.assertEqual(novos, 1)

    def test_falha_na_leitura_nao_marca_como_sincronizado(self):
        processo = self.processo()

        with self.assertRaises(DatajudErro):
            sincronizar_processo(processo, buscar=mock.Mock(side_effect=DatajudErro("x")))

        processo.refresh_from_db()
        self.assertIsNone(processo.andamentos_sincronizados_em)

    def test_marcar_a_leitura_nao_altera_atualizado_em(self):
        processo = self.processo()
        antes = Processo.objects.get(pk=processo.pk).atualizado_em

        sincronizar_processo(processo, buscar=lambda _: [])

        self.assertEqual(Processo.objects.get(pk=processo.pk).atualizado_em, antes)


class SincronizarTodosTests(AndamentosBase):
    def test_so_processos_ativos_de_escritorios_ativos(self):
        ativo = self.processo()
        self.processo(status="ARQUIVADO")
        inativo = Escritorio.objects.create(nome="Fechada", criado_por=self.user, ativo=False)
        cliente = Cliente.objects.create(escritorio=inativo, usuario=self.user, nome="C", cpf_cnpj="y")
        self.processo(escritorio=inativo, cliente=cliente)
        buscar = mock.Mock(return_value=[])

        resumo = sincronizar_todos(buscar=buscar)

        self.assertEqual(resumo, {"processos": 1, "novos": 0, "falhas": 0, "avisados": 0})
        buscar.assert_called_once_with(ativo.numero_cnj)

    def test_uma_falha_nao_interrompe_os_demais(self):
        ruim = self.processo()
        bom = self.processo()

        def buscar(numero):
            if numero == ruim.numero_cnj:
                raise DatajudErro("fora do ar")
            if numero == "boom":
                raise RuntimeError
            return _movimentos("A")

        with self.assertLogs("api.andamentos", level="WARNING"):
            resumo = sincronizar_todos(buscar=buscar)

        self.assertEqual(resumo, {"processos": 1, "novos": 1, "falhas": 1, "avisados": 0})
        self.assertEqual(bom.andamentos.count(), 1)

    def test_erro_inesperado_tambem_e_isolado(self):
        self.processo()
        self.processo()

        with self.assertLogs("api.andamentos", level="ERROR"):
            resumo = sincronizar_todos(buscar=mock.Mock(side_effect=RuntimeError))

        self.assertEqual(resumo["falhas"], 2)

    def test_limite_prioriza_quem_nunca_foi_lido(self):
        lido = self.processo(andamentos_sincronizados_em=timezone.now())
        nunca = self.processo()
        buscar = mock.Mock(return_value=[])

        sincronizar_todos(limite=1, buscar=buscar)

        buscar.assert_called_once_with(nunca.numero_cnj)
        self.assertNotEqual(nunca.pk, lido.pk)

    def test_comando_imprime_o_resumo(self):
        self.processo()
        saida = io.StringIO()

        with mock.patch("api.andamentos.consultar_movimentos", return_value=[]):
            # o default `buscar` foi fixado na definição: troca-se a função do módulo do comando
            with mock.patch("api.management.commands.sincronizar_andamentos.sincronizar_todos",
                            return_value={"processos": 3, "novos": 5, "falhas": 1, "avisados": 2}):
                call_command("sincronizar_andamentos", "--limite", "10", stdout=saida)

        self.assertIn("3 processo(s) lido(s), 5 andamento(s) novo(s), 1 falha(s), 2 pessoa(s) avisada(s).", saida.getvalue())


class AvisoDeNovosAndamentosTests(AndamentosBase):
    def _lido(self, **extra):
        """Processo que já passou por uma leitura: só o que vier depois é novidade."""
        processo = self.processo(andamentos_sincronizados_em=timezone.now(), **extra)
        Andamento.objects.create(
            processo=processo, data_hora=timezone.datetime(2024, 1, 1, tzinfo=dt_timezone.utc),
            codigo=0, nome="Antigo",
        )
        return processo

    def test_avisa_so_o_que_e_novo_e_num_unico_email_por_escritorio(self):
        a, b = self._lido(), self._lido()
        resumo = sincronizar_todos(buscar=lambda _: _movimentos("Antigo", "Sentença"))

        self.assertEqual(resumo["avisados"], 1)
        self.assertEqual(len(mail.outbox), 1)
        corpo = mail.outbox[0].body
        self.assertIn(a.numero_cnj, corpo)
        self.assertIn(b.numero_cnj, corpo)
        self.assertIn("Sentença", corpo)
        self.assertNotIn("Antigo", corpo)

    def test_primeira_leitura_nao_avisa_o_historico_inteiro(self):
        self.processo()

        resumo = sincronizar_todos(buscar=lambda _: _movimentos("A", "B", "C"))

        self.assertEqual(resumo["novos"], 3)
        self.assertEqual(resumo["avisados"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_sem_novidade_nao_manda_email(self):
        self._lido()

        resumo = sincronizar_todos(buscar=lambda _: _movimentos("Antigo"))

        self.assertEqual(resumo["avisados"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_nao_avisa_quem_saiu_do_escritorio_ou_nao_tem_email(self):
        self._lido()
        MembroEscritorio.objects.filter(usuario=self.user).update(status="SUSPENSO")

        resumo = sincronizar_todos(buscar=lambda _: _movimentos("Antigo", "Novo"))

        self.assertEqual(resumo["novos"], 1)
        self.assertEqual(resumo["avisados"], 0)

    def test_falha_no_email_nao_desfaz_a_leitura(self):
        processo = self._lido()
        avisar = mock.Mock(side_effect=OSError("smtp fora"))

        with self.assertLogs("api.andamentos", level="ERROR"):
            resumo = sincronizar_todos(buscar=lambda _: _movimentos("Antigo", "Novo"), avisar=avisar)

        self.assertEqual(resumo["avisados"], 0)
        self.assertEqual(processo.andamentos.count(), 2)

    def test_limita_a_lista_do_email_a_dez_andamentos(self):
        self._lido()
        nomes = ["Antigo"] + [f"Mov{i:02d}" for i in range(15)]

        sincronizar_todos(buscar=lambda _: _movimentos(*nomes))

        self.assertIn("e mais 5", mail.outbox[0].body)
        self.assertIn("Mov09", mail.outbox[0].body)
        self.assertNotIn("Mov14", mail.outbox[0].body)


class AndamentosEndpointTests(AndamentosBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.cabecalho = {"HTTP_X_ESCRITORIO_ID": str(self.escritorio.pk)}

    def _url(self, processo, sufixo=""):
        return f"/api/v1/processos/{processo.pk}/andamentos/{sufixo}"

    def test_lista_os_andamentos_do_mais_recente_ao_mais_antigo(self):
        processo = self.processo()
        sincronizar_processo(processo, buscar=lambda _: _movimentos("Velho", "Novo"))

        resposta = self.client.get(self._url(processo), **self.cabecalho)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual([a["nome"] for a in resposta.data["andamentos"]], ["Novo", "Velho"])
        self.assertIsNotNone(resposta.data["sincronizado_em"])

    def test_processo_de_outro_escritorio_nao_aparece(self):
        outro_dono = get_user_model().objects.create_user(username="o", email="o@x.com", password="x")
        outro = Escritorio.objects.create(nome="Outra", criado_por=outro_dono)
        cliente = Cliente.objects.create(escritorio=outro, usuario=outro_dono, nome="C", cpf_cnpj="y")
        alheio = self.processo(escritorio=outro, cliente=cliente)

        leitura = self.client.get(self._url(alheio), **self.cabecalho)
        escrita = self.client.post(self._url(alheio, "sincronizar/"), **self.cabecalho)

        self.assertEqual(leitura.status_code, 404)
        self.assertEqual(escrita.status_code, 404)

    def test_sincronizar_devolve_a_lista_e_quantos_eram_novos(self):
        processo = self.processo()
        with mock.patch("api.views.sincronizar_processo") as sincronizar:
            def grava(p):
                Andamento.objects.create(processo=p, data_hora=timezone.now(), nome="X")
                return 1
            sincronizar.side_effect = grava

            resposta = self.client.post(self._url(processo, "sincronizar/"), **self.cabecalho)

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data["novos"], 1)
        self.assertEqual(len(resposta.data["andamentos"]), 1)

    def test_erro_do_datajud_vira_resposta_clara_sem_derrubar(self):
        processo = self.processo()
        casos = ((DatajudNaoConfigurado("sem chave"), 503), (TribunalNaoSuportado("fora"), 400),
                 (DatajudErro("indisponível"), 502))

        for excecao, esperado in casos:
            with self.subTest(erro=type(excecao).__name__):
                with mock.patch("api.views.sincronizar_processo", side_effect=excecao):
                    resposta = self.client.post(self._url(processo, "sincronizar/"), **self.cabecalho)
                self.assertEqual(resposta.status_code, esperado)
                self.assertEqual(resposta.data["detail"], str(excecao))

    def test_sincronizar_tem_limite_de_requisicoes(self):
        processo = self.processo()
        with mock.patch("api.views.sincronizar_processo", return_value=0):
            codigos = [
                self.client.post(self._url(processo, "sincronizar/"), **self.cabecalho).status_code
                for _ in range(31)
            ]

        self.assertEqual(codigos[29], 200)
        self.assertEqual(codigos[30], 429)

    def test_exige_login(self):
        processo = self.processo()

        resposta = APIClient().post(self._url(processo, "sincronizar/"), **self.cabecalho)

        self.assertEqual(resposta.status_code, 401)
