#!/bin/sh
# Mantém um processo no ar, depois que o site responde. Chamado pelo iniciar.sh com env -i:
# este script também não pode herdar as chaves do Django.
until [ -e /tmp/site-pronto ]; do sleep 1; done
while :; do
    "$@"
    echo "Processo encerrado, reiniciando em 5 s: $*"
    sleep 5
done
