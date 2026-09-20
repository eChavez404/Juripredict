# publicacao/

Saída de `dataset/pipeline/exportar_dataset.py`. Pasta versionada, conteúdo não.

```bash
cd dataset/pipeline
python exportar_dataset.py --entrada ../data/dataset.csv --saida ../../publicacao
```

Gera três arquivos:

| Arquivo | Publicável | O que é |
|---|---|---|
| `juripredict_insalubridade.csv` | sim | uma linha por processo × pedido, sem texto e sem identificador direto |
| `DATASET_CARD.md` | sim | procedência, limitações conhecidas e o que o conjunto **não** é |
| `_mapa_unidades_NAO_PUBLICAR.csv` | **não** | desfaz a pseudonimização das unidades julgadoras |

O terceiro arquivo existe para uso interno — conferir uma estimativa contra a
vara real. Ele reverte `unidade_01` para o nome da unidade e, por isso, está
bloqueado no `.gitignore` por padrão de nome. Não versione, não anexe, não
compartilhe junto do CSV.

A versão de trabalho (`dataset/data/dataset.csv`) e a versão publicável são
arquivos diferentes de propósito: a primeira carrega texto integral, número CNJ
e evidências; a segunda, só o tabulado. Ver a docstring do exportador para o
motivo.
