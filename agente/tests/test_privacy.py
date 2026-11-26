"""Dados pessoais de um contrato de trabalho, nos formatos reais, contra o mascaramento."""

# ruff: noqa: E501 (o contrato fica como o advogado o colaria)

import unittest

from app.core.privacy import mask_documents

# Dados fictícios, nos formatos que um contrato de trabalho e uma petição trazem.
CONTRATO = """CONTRATO INDIVIDUAL DE TRABALHO
EMPREGADOR: HOSPITAL SANTA LUZIA LTDA, inscrito no CNPJ sob o nº 12.345.678/0001-90, com sede na Rua das Flores, nº 120, Centro, Balsas/MA, CEP 65800-000.
EMPREGADO: MARIA DAS GRAÇAS PEREIRA SOUSA, brasileira, solteira, auxiliar de limpeza, portadora do RG nº 1234567 SSP/MA e do CPF nº 123.456.789-09, CTPS nº 1234567 série 0012-MA, PIS 123.45678.90-1, nascida em 12/03/1988, residente na Rua Dois, Quadra 5, Casa 12, Bairro São Félix, Balsas/MA, CEP 65800-123, telefone (99) 98123-4567, e-mail maria.sousa@gmail.com.
Cláusula 1ª. Função de auxiliar de limpeza hospitalar, com limpeza diária de banheiros coletivos e recolhimento de lixo hospitalar, a partir de 01/02/2022.
Cláusula 2ª. Salário mensal de R$ 1.518,00, pago no Banco do Brasil, agência 1234-5, conta corrente 98765-4.
Cláusula 3ª. Jornada de 44 horas semanais.
Testemunhas: José Ribamar Costa, CPF 98765432100; Ana Lúcia Ferreira, RG 0987654 SSP-MA.
Advogado do empregador: Dr. Carlos Alberto Mendes, OAB/MA nº 12.345.
CNH 01234567890. Título de eleitor 0123 4567 8901.
"""

SENSIVEIS = {
    "nome da empregada": "MARIA DAS GRAÇAS",
    "nome do empregador": "SANTA LUZIA",
    "nome de testemunha": "José Ribamar",
    "nome de testemunha, antes do RG": "Ana Lúcia",
    "nome do advogado": "Carlos Alberto",
    "CNPJ": "12.345.678/0001-90",
    "CPF formatado": "123.456.789-09",
    "CPF só com números": "98765432100",
    "RG": "1234567 SSP",
    "RG da testemunha": "0987654",
    "CTPS": "série 0012",
    "PIS": "123.45678.90-1",
    "nascimento": "12/03/1988",
    "endereço": "Quadra 5, Casa 12",
    "endereço da empresa": "Rua das Flores",
    "CEP": "65800-123",
    "telefone": "98123-4567",
    "e-mail": "maria.sousa",
    "agência": "1234-5",
    "conta": "98765-4",
    "OAB": "12.345",
    "CNH": "01234567890",
    "título de eleitor": "0123 4567 8901",
}
FATOS_DO_CASO = [
    "auxiliar de limpeza",
    "lixo hospitalar",
    "01/02/2022",
    "R$ 1.518,00",
    "44 horas",
    "[OAB].",  # o ponto final da frase fica
]


class ContratoTests(unittest.TestCase):
    def test_nenhum_dado_pessoal_passa(self):
        saida = mask_documents(CONTRATO)
        for nome, trecho in SENSIVEIS.items():
            with self.subTest(nome):
                self.assertNotIn(trecho, saida)

    def test_fatos_do_caso_ficam(self):
        saida = mask_documents(CONTRATO)
        for trecho in FATOS_DO_CASO:
            with self.subTest(trecho):
                self.assertIn(trecho, saida)


class FalsosPositivosTests(unittest.TestCase):
    """Texto jurídico comum que não é dado pessoal, tirado das sentenças do TRT-16."""

    def test_texto_juridico_fica_intacto(self):
        for texto in (
            "nos termos do art. 818 da CLT c/c art. 373, I do CPC",
            "a perita não conseguiu encontrar o endereço da reclamada",
            "Processo 0016123-45.2024.5.16.0001, Vara do Trabalho de Balsas",
            "trabalhou de 2019-2024 como auxiliar de limpeza",
            "levando em conta 2 fatores, a Súmula 448, II, do TST",
            "Reclamante: auxiliar de limpeza em hospital",
        ):
            with self.subTest(texto):
                self.assertEqual(mask_documents(texto), texto)

    def test_nome_de_perito_na_sentenca(self):
        self.assertEqual(
            mask_documents("o Sr. João Batista constatou in loco"), "o Sr. [NOME] constatou in loco"
        )


if __name__ == "__main__":
    unittest.main()
