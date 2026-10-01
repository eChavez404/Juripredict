from django.db import transaction

from .services import registrar_evento_auditoria


class AuditoriaCrudMixin:
    recurso_auditoria = None

    def _recurso_tipo(self, instance):
        return self.recurso_auditoria or instance._meta.model_name

    @transaction.atomic
    def perform_create(self, serializer):
        instance = serializer.save()
        registrar_evento_auditoria(
            escritorio=instance.escritorio,
            ator=self.request.user,
            acao=f"{self._recurso_tipo(instance)}.criado",
            recurso_tipo=self._recurso_tipo(instance),
            recurso_id=instance.pk,
        )

    @transaction.atomic
    def perform_update(self, serializer):
        campos = sorted(
            campo
            for campo in serializer.validated_data
            if campo not in {"cpf_cnpj", "arquivo_peticao_inicial"}
        )
        instance = serializer.save()
        registrar_evento_auditoria(
            escritorio=instance.escritorio,
            ator=self.request.user,
            acao=f"{self._recurso_tipo(instance)}.atualizado",
            recurso_tipo=self._recurso_tipo(instance),
            recurso_id=instance.pk,
            alteracoes={"campos": campos},
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        escritorio = instance.escritorio
        recurso_id = instance.pk
        recurso_tipo = self._recurso_tipo(instance)
        instance.delete()
        registrar_evento_auditoria(
            escritorio=escritorio,
            ator=self.request.user,
            acao=f"{recurso_tipo}.excluido",
            recurso_tipo=recurso_tipo,
            recurso_id=recurso_id,
        )

