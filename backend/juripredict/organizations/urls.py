from django.urls import path

from .views import MembroEscritorioViewSet


membros_list = MembroEscritorioViewSet.as_view({"get": "list"})
membro_detail = MembroEscritorioViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update"}
)

urlpatterns = [
    path(
        "escritorios/<uuid:escritorio_id>/membros/",
        membros_list,
        name="membro-escritorio-list",
    ),
    path(
        "escritorios/<uuid:escritorio_id>/membros/<uuid:pk>/",
        membro_detail,
        name="membro-escritorio-detail",
    ),
]

