import csv
import io
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.tokens_api import criar_token_api
from auditlog.models import EventoAuditoria
from organizations.models import Escritorio, MembroEscritorio

from .models import Andamento, Cliente, EventoAgenda, Processo


class Base(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user("a@e.invalid", "a@e.invalid", "x")
        self.escritorio = Escritorio.objects.create(nome="A", criado_por=self.usuario)
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.usuario, papel=MembroEscritorio.Papel.OWNER
        )
        self.cliente = Cliente.objects.create(
            escritorio=self.escritorio, nome="Cliente", cpf_cnpj="x", cpf_cnpj_hash="h"
        )
        self.api = self._api(self.usuario)
        self._n = 0

    def _api(self, usuario):
        api = APIClient()
        api.force_authenticate(usuario)
        return api

    def processo(self, *, escritorio=None, cliente=None, **campos):
        self._n += 1
        padrao = {
            "numero_cnj": f"{self._n:07d}-00.2026.5.16.0001",
            "vara": "1ª Vara",
            "comarca": "Balsas",
            "parte_contraria": "Empresa",
            "resultado": "FAVORAVEL",
            "status": "ARQUIVADO",
        }
        return Processo.objects.create(
            escritorio=escritorio or self.escritorio,
            cliente=cliente or self.cliente,
            **{**padrao, **campos},
        )

    def outro_escritorio(self):
        dono = get_user_model().objects.create_user("b@e.invalid", "b@e.invalid", "x")
        escritorio = Escritorio.objects.create(nome="B", criado_por=dono)
        MembroEscritorio.objects.create(
            escritorio=escritorio, usuario=dono, papel=MembroEscritorio.Papel.OWNER
        )
        cliente = Cliente.objects.create(
            escritorio=escritorio, nome="Alheio", cpf_cnpj="y", cpf_cnpj_hash="h2"
        )
        return escritorio, cliente

    def estagiario(self):
        pessoa = get_user_model().objects.create_user("e@e.invalid", "e@e.invalid", "x")
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=pessoa, papel=MembroEscritorio.Papel.ESTAGIARIO
        )
        return self._api(pessoa)


class RecortesTests(Base):
    def setUp(self):
        super().setUp()
        for _ in range(10):
            self.processo(area="TRABALHISTA", data_distribuicao=date(2024, 5, 1))
        for _ in range(4):
            self.processo(area="CIVEL", resultado="DESFAVORAVEL", data_distribuicao=date(2025, 5, 1))
        self.processo(area="CIVEL", resultado="ACORDO", vara="2ª Vara")  # sem data
        self.processo(area="CIVEL", resultado="PENDENTE", status="ATIVO", data_distribuicao=date(2025, 5, 1))

    def _get(self, **params):
        resposta = self.api.get("/api/v1/jurimetria/", params)
        self.assertEqual(resposta.status_code, 200, resposta.data)
        return resposta.data

    def test_sem_filtro_considera_toda_a_carteira_concluida(self):
        dados = self._get()
        self.assertEqual(dados["total_analisados"], 15)
        self.assertEqual(dados["filtros"], {"area": None, "ano": None})

    def test_filtro_por_area(self):
        dados = self._get(area="TRABALHISTA")
        self.assertEqual(dados["total_analisados"], 10)
        self.assertEqual(dados["taxa_favoravel"], 100)
        self.assertIsNotNone(dados["intervalo_favoravel"])

    def test_recorte_abaixo_do_piso_suprime_a_taxa_mesmo_com_carteira_grande(self):
        dados = self._get(area="CIVEL")
        self.assertEqual(dados["total_analisados"], 5)
        self.assertIsNone(dados["taxa_favoravel"])
        self.assertFalse(dados["amostra_suficiente"])

    def test_filtro_por_ano_e_sem_data(self):
        self.assertEqual(self._get(ano="2024")["total_analisados"], 10)
        self.assertEqual(self._get(ano="sem_data")["total_analisados"], 1)

    def test_por_ano_vem_do_mais_recente_e_sem_data_por_ultimo(self):
        anos = [(item["ano"], item["total"], item["suficiente"]) for item in self._get()["por_ano"]]
        self.assertEqual(anos, [(2025, 4, False), (2024, 10, True), (None, 1, False)])

    def test_por_ano_abaixo_do_piso_nao_traz_taxa(self):
        por_ano = {item["ano"]: item for item in self._get()["por_ano"]}
        self.assertIsNone(por_ano[2025]["favoravel"])
        self.assertIn("Amostra insuficiente", por_ano[2025]["motivo"])

    def test_todas_as_varas_vem_na_resposta(self):
        for i in range(12):
            self.processo(vara=f"Vara {i:02d}")
        self.assertEqual(len(self._get()["por_vara"]), 14)

    def test_opcoes_mostram_o_que_existe_mesmo_com_filtro_aplicado(self):
        opcoes = self._get(area="CIVEL")["opcoes"]
        self.assertEqual([a["valor"] for a in opcoes["areas"]], ["CIVEL", "TRABALHISTA"])
        self.assertEqual(opcoes["anos"], [2025, 2024])

    def test_filtro_invalido_e_recusado(self):
        for params in ({"area": "X"}, {"ano": "abc"}, {"ano": "99999"}, {"ano": "٢٠٢٤"}):
            self.assertEqual(self.api.get("/api/v1/jurimetria/", params).status_code, 400, params)


class RastreabilidadeTests(Base):
    def _get(self, **params):
        return self.api.get("/api/v1/jurimetria/processos/", params)

    def test_lista_os_concluidos_do_recorte_e_nao_os_pendentes(self):
        alvo = self.processo(vara="1ª Vara", data_distribuicao=date(2024, 1, 1))
        self.processo(vara="1ª Vara", resultado="PENDENTE")
        self.processo(vara="2ª Vara")

        dados = self._get(vara="1ª Vara").data

        self.assertEqual(dados["total"], 1)
        self.assertEqual(dados["processos"][0]["id"], alvo.pk)
        self.assertEqual(dados["processos"][0]["cliente_nome"], "Cliente")

    def test_a_soma_da_lista_bate_com_o_n_exibido(self):
        for _ in range(3):
            self.processo(vara="1ª Vara", data_distribuicao=date(2024, 1, 1))
        self.processo(vara="1ª Vara", resultado="DESFAVORAVEL", data_distribuicao=date(2025, 1, 1))
        por_vara = self.api.get("/api/v1/jurimetria/").data["por_vara"][0]
        self.assertEqual(self._get(vara="1ª Vara").data["total"], por_vara["total"])
        self.assertEqual(self._get(vara="1ª Vara", ano="2024").data["total"], 3)
        self.assertEqual(self._get(vara="1ª Vara", resultado="DESFAVORAVEL").data["total"], 1)

    def test_nao_expoe_valor_da_causa(self):
        self.processo(valor_causa="1000.00")
        self.assertNotIn("valor_causa", self._get().data["processos"][0])

    def test_nao_mostra_processo_de_outro_escritorio(self):
        escritorio, cliente = self.outro_escritorio()
        self.processo(escritorio=escritorio, cliente=cliente)
        self.assertEqual(self._get().data["total"], 0)

    def test_estagiario_nao_acessa(self):
        self.assertEqual(self.estagiario().get("/api/v1/jurimetria/processos/").status_code, 403)

    def test_resultado_invalido_e_recusado(self):
        self.assertEqual(self._get(resultado="PENDENTE").status_code, 400)


class ExportacaoTests(Base):
    def _csv(self, **params):
        resposta = self.api.get("/api/v1/jurimetria/exportar/", params)
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("text/csv", resposta["Content-Type"])
        self.assertIn("attachment", resposta["Content-Disposition"])
        texto = resposta.content.decode("utf-8")
        self.assertTrue(texto.startswith("﻿"))
        return list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))

    def _dados(self, linhas):
        indice = next(i for i, linha in enumerate(linhas) if linha[:1] == ["Recorte"])
        return linhas[indice + 1 :]

    def test_taxa_exportada_leva_o_n_e_o_intervalo(self):
        for _ in range(10):
            self.processo(data_distribuicao=date(2024, 1, 1))
        total = self._dados(self._csv())[0]
        self.assertEqual(total[:3], ["Carteira", "Total", "10"])
        self.assertEqual(total[6:9], ["100", "72", "100"])

    def test_abaixo_do_piso_sai_sem_taxa_e_com_o_motivo(self):
        self.processo()
        total = self._dados(self._csv())[0]
        self.assertEqual(total[6:9], ["", "", ""])
        self.assertIn("Amostra insuficiente", total[9])

    def test_separa_favoraveis_de_acordos(self):
        self.processo(resultado="ACORDO")
        self.processo(resultado="FAVORAVEL")
        self.assertEqual(self._dados(self._csv())[0][3:6], ["1", "1", "0"])

    def test_vara_maliciosa_nao_vira_formula_na_planilha(self):
        for vara in ("=CMD()", "+1", "-1", "@SOMA(A1)"):
            self.processo(vara=vara)
        grupos = [linha[1] for linha in self._dados(self._csv()) if linha[0] == "Vara"]
        self.assertTrue(grupos)
        for grupo in grupos:
            self.assertTrue(grupo.startswith("'"), grupo)

    def test_respeita_o_filtro_e_descreve_o_recorte(self):
        self.processo(area="CIVEL")
        self.processo(area="TRABALHISTA")
        linhas = self._csv(area="CIVEL")
        self.assertIn("Área: Cível", linhas[0][1])
        self.assertEqual(self._dados(linhas)[0][2], "1")

    def test_exportar_fica_na_auditoria(self):
        self._csv(area="CIVEL")
        evento = EventoAuditoria.objects.get(acao="jurimetria.exportada")
        self.assertEqual(evento.ator, self.usuario)
        self.assertEqual(evento.alteracoes, {"recorte": "Área: Cível"})

    def test_estagiario_nao_exporta(self):
        self.assertEqual(self.estagiario().get("/api/v1/jurimetria/exportar/").status_code, 403)


class TokenDeApiNasRotasNovasTests(Base):
    def setUp(self):
        super().setUp()
        self.usuario.set_password("Senha#Forte2026x")
        self.usuario.save()
        _, texto = criar_token_api(usuario=self.usuario, nome="Agente", senha="Senha#Forte2026x")
        self.agente = APIClient()
        self.agente.credentials(
            HTTP_AUTHORIZATION=f"Bearer {texto}", HTTP_X_ESCRITORIO_ID=str(self.escritorio.pk)
        )

    def test_le_as_rotas_de_consulta_e_cada_leitura_entra_na_auditoria(self):
        for rota in (
            "/api/v1/pendencias/",
            "/api/v1/jurimetria/processos/",
            "/api/v1/prazos/calcular/?data_base=2026-03-09&dias=5",
        ):
            self.assertEqual(self.agente.get(rota).status_code, 200, rota)
        self.assertEqual(EventoAuditoria.objects.filter(acao="token_api.leitura").count(), 3)

    def test_filtro_entra_na_auditoria_so_pelo_nome(self):
        self.agente.get("/api/v1/jurimetria/processos/", {"vara": "Vara do João"})
        evento = EventoAuditoria.objects.get(acao="token_api.leitura")
        self.assertEqual(evento.alteracoes["filtros"], ["vara"])
        self.assertNotIn("João", str(evento.alteracoes))

    def test_exportacao_fica_fora_do_alcance_do_token(self):
        self.assertEqual(self.agente.get("/api/v1/jurimetria/exportar/").status_code, 403)


class PendenciasTests(Base):
    def _evento(self, dias, *, tipo="PRAZO", escritorio=None, **campos):
        return EventoAgenda.objects.create(
            escritorio=escritorio or self.escritorio,
            usuario=self.usuario,
            titulo=f"{tipo} {dias}",
            tipo=tipo,
            inicio=timezone.now() + timedelta(days=dias),
            **campos,
        )

    def _get(self):
        resposta = self.api.get("/api/v1/pendencias/")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        return resposta.data

    def test_separa_vencidos_de_proximos(self):
        vencido = self._evento(-3)
        proximo = self._evento(3)
        self._evento(30)  # longe demais

        dados = self._get()

        self.assertEqual([e["id"] for e in dados["vencidos"]], [vencido.pk])
        self.assertEqual([e["id"] for e in dados["proximos"]], [proximo.pk])
        self.assertEqual(dados["urgentes"], 1)

    def test_prazo_de_hoje_ja_passado_no_horario_ainda_nao_esta_vencido(self):
        agora = timezone.localtime()
        cedo = agora.replace(hour=0, minute=0, second=1)
        evento = EventoAgenda.objects.create(
            escritorio=self.escritorio, usuario=self.usuario, titulo="Hoje", tipo="PRAZO", inicio=cedo
        )
        dados = self._get()
        self.assertEqual(dados["vencidos"], [])
        self.assertEqual([e["id"] for e in dados["proximos"]], [evento.pk])
        self.assertEqual(dados["urgentes"], 1)

    def test_concluido_e_reuniao_nao_contam(self):
        self._evento(-1, concluido=True)
        self._evento(1, tipo="REUNIAO")
        dados = self._get()
        self.assertEqual((dados["urgentes"], dados["vencidos"], dados["proximos"]), (0, [], []))

    def test_audiencia_passada_nao_vira_prazo_vencido(self):
        self._evento(-1, tipo="AUDIENCIA")
        self.assertEqual(self._get()["vencidos"], [])

    def test_totais_seguem_certos_quando_a_lista_e_cortada(self):
        for _ in range(25):
            self._evento(-1)
        dados = self._get()
        self.assertEqual((dados["total_vencidos"], len(dados["vencidos"])), (25, 20))
        self.assertEqual(dados["urgentes"], 25)

    def test_andamentos_recentes_do_escritorio(self):
        processo = self.processo()
        novo = Andamento.objects.create(processo=processo, data_hora=timezone.now(), nome="Novo")
        Andamento.objects.create(processo=processo, data_hora=timezone.now() - timedelta(days=30), nome="Velho")
        dados = self._get()["andamentos_recentes"]
        self.assertEqual([a["id"] for a in dados], [novo.pk])
        self.assertEqual(dados[0]["processo_numero"], processo.numero_cnj)

    def test_nao_mistura_escritorios(self):
        escritorio, cliente = self.outro_escritorio()
        self._evento(-1, escritorio=escritorio)
        alheio = self.processo(escritorio=escritorio, cliente=cliente)
        Andamento.objects.create(processo=alheio, data_hora=timezone.now(), nome="Alheio")
        dados = self._get()
        self.assertEqual((dados["urgentes"], dados["andamentos_recentes"]), (0, []))
