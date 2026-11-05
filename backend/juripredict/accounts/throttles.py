import hashlib
from collections.abc import Mapping

from rest_framework.throttling import SimpleRateThrottle


class ContaLoginThrottle(SimpleRateThrottle):
    """Limita tentativas de login por CONTA, não por IP.

    O limite por IP sozinho não segura um ataque distribuído, e baixo demais
    trava um escritório inteiro que compartilha a mesma saída de rede. Por conta,
    quem erra a senha do colega espera um minuto; quem tenta adivinhar a senha de
    alguém esbarra no teto, de onde quer que venha.
    """

    scope = "login_conta"

    def get_cache_key(self, request, view):
        # JSON que não é objeto chega até aqui: quem responde 400 é o serializer, depois
        dados = request.data if isinstance(request.data, Mapping) else {}
        login = str(dados.get("username") or dados.get("email") or "")
        login = login.strip().lower()
        if not login:
            return None
        ident = hashlib.sha256(login.encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": ident}
