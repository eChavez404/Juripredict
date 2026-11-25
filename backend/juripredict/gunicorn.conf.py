"""Lido pelo gunicorn ao iniciar, a partir da pasta do projeto.

O agente de IA roda no mesmo contêiner, com o mesmo usuário. Sem isto, ele poderia ler as
chaves do Django em /proc/<pid>/environ. Os workers herdam a marca do processo principal.
"""

import ctypes
from pathlib import Path

PR_SET_DUMPABLE = 4
ctypes.CDLL(None).prctl(PR_SET_DUMPABLE, 0)


def post_worker_init(worker):
    """O site já responde: o iniciar.sh pode ligar o agente."""
    Path("/tmp/site-pronto").touch()
