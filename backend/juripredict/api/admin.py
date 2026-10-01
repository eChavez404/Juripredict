from django.contrib import admin

from .models import Cliente, EventoAgenda, Processo


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "email", "usuario", "criado_em")
    search_fields = ("nome", "email")
    list_filter = ("tipo",)


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = ("numero_cnj", "cliente", "area", "status", "resultado", "usuario")
    search_fields = ("numero_cnj", "cliente__nome", "parte_contraria")
    list_filter = ("status", "resultado", "area")


@admin.register(EventoAgenda)
class EventoAgendaAdmin(admin.ModelAdmin):
    list_display = ("titulo", "tipo", "inicio", "concluido", "usuario")
    search_fields = ("titulo", "processo__numero_cnj")
    list_filter = ("tipo", "concluido")
