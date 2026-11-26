import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import indexar
from app.core.vector_store import RetrievedCase


def _trecho(i, **campos):
    return {
        "id": f"doc{i}:insalubridade#0",
        "id_sentenca": f"doc{i}:insalubridade",
        "numero_cnj": f"{i:07d}-00.2025.5.16.0011",
        "tipo_documento": "Sentença",
        "orgao_julgador": "Vara do Trabalho de Balsas",
        "data_julgamento": "2025-05-10",
        "resultado": "deferido",
        "tema": "insalubridade",
        "texto": "laudo favorável, grau máximo",
        **campos,
    }


class IndexarTests(unittest.TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())
        self.arquivo = self.pasta / "rag.jsonl"
        trechos = [_trecho(1), _trecho(2, numero_cnj="", data_julgamento=None)]
        self.arquivo.write_text("".join(json.dumps(t) + "\n" for t in trechos), encoding="utf-8")
        self.pinecone = MagicMock()
        self.pinecone.has_index.return_value = False
        self.genai = MagicMock()
        self.genai.models.embed_content.side_effect = lambda **kw: SimpleNamespace(
            embeddings=[SimpleNamespace(values=[0.1] * 3) for _ in kw["contents"]]
        )
        configurado = patch.multiple(indexar, PINECONE_API_KEY="k", PINECONE_INDEX="casos")
        configurado.start()
        self.addCleanup(configurado.stop)

    def test_cota_esgotada_espera_e_tenta_de_novo(self):
        from google.genai.errors import ClientError

        sucesso = self.genai.models.embed_content.side_effect
        respostas = iter([ClientError(429, {"error": {"message": "quota"}}), None])

        def falha_uma_vez(**kw):
            erro = next(respostas)
            if erro:
                raise erro
            return sucesso(**kw)

        self.genai.models.embed_content.side_effect = falha_uma_vez
        with patch.object(indexar.time, "sleep") as dormir:
            self.assertEqual(self.rodar(), 2)
        dormir.assert_called_once_with(indexar.ESPERA_COTA_SEGUNDOS)

    def test_cota_diaria_para_e_guarda_o_que_ja_foi(self):
        from google.genai.errors import ClientError

        diaria = ClientError(429, {"error": {"message": "quotaId: EmbedContentRequestsPerDay"}})
        self.genai.models.embed_content.side_effect = diaria
        with self.assertRaises(SystemExit) as parada:
            self.rodar()
        self.assertIn("Rode de novo amanhã", str(parada.exception))

    def test_limite_envia_so_parte_e_retoma_o_resto(self):
        self.assertEqual(
            indexar.indexar(
                self.arquivo, pinecone=self.pinecone, genai=self.genai, pausa=0, limite=1
            ),
            1,
        )
        self.assertEqual(self.rodar(), 1)

    def rodar(self):
        return indexar.indexar(self.arquivo, pinecone=self.pinecone, genai=self.genai, pausa=0)

    def test_cria_o_indice_envia_no_formato_da_busca_e_retoma_sem_repetir(self):
        self.assertEqual(self.rodar(), 2)

        self.pinecone.create_index.assert_called_once()
        self.assertEqual(self.pinecone.create_index.call_args.kwargs["metric"], "cosine")
        vetores = self.pinecone.Index.return_value.upsert.call_args.kwargs["vectors"]
        self.assertEqual(
            [v["id"] for v in vetores], ["doc1:insalubridade#0", "doc2:insalubridade#0"]
        )
        # o que a busca lê precisa passar pelo contrato dela
        for vetor in vetores:
            RetrievedCase.model_validate({**vetor["metadata"], "similaridade": 0.5})
            self.assertNotIn(None, vetor["metadata"].values())
            self.assertEqual(vetor["metadata"]["temas"], ["insalubridade"])
        enviado = self.genai.models.embed_content.call_args.kwargs["contents"][0].parts[0].text
        self.assertTrue(
            enviado.startswith("title: insalubridade · Vara do Trabalho de Balsas | text: ")
        )

        self.assertEqual(self.rodar(), 0)
        self.assertEqual(self.pinecone.Index.return_value.upsert.call_count, 1)

    def test_sem_chaves_do_pinecone_para_antes_de_chamar_o_google(self):
        with patch.object(indexar, "PINECONE_INDEX", ""), self.assertRaises(SystemExit):
            self.rodar()
        self.genai.models.embed_content.assert_not_called()


if __name__ == "__main__":
    unittest.main()
