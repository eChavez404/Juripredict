"""Lido pelo gunicorn ao iniciar, a partir da pasta do projeto.

O agente de IA e o servidor MCP rodam no mesmo contêiner, com o mesmo usuário. Sem a marca
abaixo, poderiam ler as chaves do Django em /proc/<pid>/environ. Os workers a herdam.
"""

import ctypes
from pathlib import Path

PR_SET_DUMPABLE = 4
ctypes.CDLL(None).prctl(PR_SET_DUMPABLE, 0)

# O esquema (https) continua vindo só do SECURE_PROXY_SSL_HEADER do Django. O padrão passaria a
# confiar em cabeçalhos do cliente, agora que toda requisição chega pelo nginx, em 127.0.0.1.
forwarded_allow_ips = ""


def post_worker_init(worker):
    """O site já responde: o manter.sh pode ligar os outros processos."""
    Path("/tmp/site-pronto").touch()
