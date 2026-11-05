from django.conf import settings
from rest_framework import serializers

# Os primeiros bytes de cada formato. A extensão sozinha é só o nome que o
# cliente escolheu: um executável renomeado para ".pdf" passaria por ela.
ASSINATURAS = {
    "pdf": (b"%PDF",),
    "docx": (b"PK\x03\x04",),  # DOCX é um zip
    "doc": (b"\xd0\xcf\x11\xe0",),  # contêiner OLE do Word antigo
}


def validar_documento(arquivo):
    """Confere tamanho, extensão e conteúdo do arquivo enviado."""
    limite = settings.UPLOAD_MAX_BYTES
    if arquivo.size > limite:
        raise serializers.ValidationError(
            f"O arquivo deve ter no máximo {limite // (1024 * 1024)} MB."
        )

    nome = arquivo.name or ""
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if extensao not in ASSINATURAS:
        raise serializers.ValidationError("Envie um arquivo PDF, DOC ou DOCX.")

    cabecalho = arquivo.read(8)
    arquivo.seek(0)
    if not cabecalho.startswith(ASSINATURAS[extensao]):
        raise serializers.ValidationError(
            "O conteúdo do arquivo não corresponde à extensão informada."
        )
    return arquivo


# Nome antigo, de quando só a petição inicial era enviada.
validar_peticao_inicial = validar_documento
