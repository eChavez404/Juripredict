from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.exceptions import ValidationError

from .validators import validar_peticao_inicial

PDF = b"%PDF-1.7\n conteudo"
DOCX = b"PK\x03\x04 conteudo"
DOC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 conteudo"


def _arquivo(nome, conteudo):
    return SimpleUploadedFile(nome, conteudo)


class ValidarPeticaoInicialTests(SimpleTestCase):
    def test_aceita_os_tres_formatos_com_conteudo_correto(self):
        for nome, conteudo in (("a.pdf", PDF), ("a.docx", DOCX), ("a.doc", DOC)):
            with self.subTest(nome):
                arquivo = _arquivo(nome, conteudo)
                self.assertIs(validar_peticao_inicial(arquivo), arquivo)

    def test_extensao_e_maiuscula_sao_tratadas_sem_diferenca(self):
        validar_peticao_inicial(_arquivo("PETICAO.PDF", PDF))

    def test_rejeita_executavel_renomeado_para_pdf(self):
        with self.assertRaisesMessage(ValidationError, "não corresponde"):
            validar_peticao_inicial(_arquivo("inocente.pdf", b"MZ\x90\x00 executavel"))

    def test_rejeita_conteudo_de_um_formato_com_extensao_de_outro(self):
        with self.assertRaises(ValidationError):
            validar_peticao_inicial(_arquivo("a.pdf", DOCX))

    def test_rejeita_extensao_fora_da_lista(self):
        for nome in ("a.exe", "a.txt", "a.pdf.exe", "semextensao"):
            with self.subTest(nome), self.assertRaisesMessage(ValidationError, "PDF, DOC ou DOCX"):
                validar_peticao_inicial(_arquivo(nome, PDF))

    @override_settings(UPLOAD_MAX_BYTES=100)
    def test_rejeita_arquivo_acima_do_limite(self):
        with self.assertRaisesMessage(ValidationError, "no máximo"):
            validar_peticao_inicial(_arquivo("a.pdf", PDF + b"x" * 200))

    def test_devolve_o_ponteiro_ao_inicio_para_o_armazenamento_ler_tudo(self):
        arquivo = _arquivo("a.pdf", PDF)

        validar_peticao_inicial(arquivo)

        self.assertEqual(arquivo.read(), PDF)
