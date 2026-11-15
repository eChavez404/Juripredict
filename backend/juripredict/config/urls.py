"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.views_oauth import (
    IntrospeccaoOAuthAPIView,
    MetadadosOAuthAPIView,
    RegistroClienteOAuthAPIView,
    RevogarOAuthAPIView,
    TokenOAuthAPIView,
)


def health_check(_request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path('health/', health_check, name='health-check'),
    path('admin/', admin.site.urls),
    path('api/v1/', include('accounts.urls')),
    path('api/v1/', include('api.urls')),
    # Conector MCP remoto: protocolo OAuth 2.1 (accounts/oauth.py). Sem barra final,
    # como os aplicativos chamam; a tela de consentimento é a rota /autorizar do SPA.
    path('.well-known/oauth-authorization-server', MetadadosOAuthAPIView.as_view(), name='oauth-metadados'),
    path('oauth/registrar', RegistroClienteOAuthAPIView.as_view(), name='oauth-registrar'),
    path('oauth/token', TokenOAuthAPIView.as_view(), name='oauth-token'),
    path('oauth/revogar', RevogarOAuthAPIView.as_view(), name='oauth-revogar'),
    path('oauth/introspeccao', IntrospeccaoOAuthAPIView.as_view(), name='oauth-introspeccao'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # Só em desenvolvimento: em produção, a referência é o backend/openapi.yaml.
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    ]

frontend_index = settings.BASE_DIR / "frontend_dist" / "index.html"
if frontend_index.exists():
    urlpatterns += [
        re_path(
            r"^(?!api/|admin/|health/|media/|static/|oauth/|\.well-known/).*$",
            TemplateView.as_view(template_name="index.html"),
            name="frontend",
        )
    ]
