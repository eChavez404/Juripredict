from django.urls import path

from .views import ConviteEscritorioViewSet, MembroEscritorioViewSet


membros_list = MembroEscritorioViewSet.as_view({"get": "list"})
membro_detail = MembroEscritorioViewSet.as_view(
    {"get": "retrieve", "patch": "partial_update"}
)

convites_list = ConviteEscritorioViewSet.as_view({"get": "list", "post": "create"})
convite_detail = ConviteEscritorioViewSet.as_view({"delete": "destroy"})

urlpatterns = [
    path(
        "escritorios/<uuid:escritorio_id>/convites/",
        convites_list,
        name="convite-escritorio-list",
    ),
    path(
        "escritorios/<uuid:escritorio_id>/convites/<uuid:pk>/",
        convite_detail,
        name="convite-escritorio-detail",
    ),
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

