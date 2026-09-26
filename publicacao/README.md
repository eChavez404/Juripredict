# publicacao/

Saída de `dataset/pipeline/exportar_dataset.py`. Pasta versionada, conteúdo não.

```bash
cd dataset/pipeline
python exportar_dataset.py --entrada dados/dataset.csv --saida ../../publicacao
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

A versão de trabalho (`dataset/pipeline/dados/dataset.csv`) e a versão
publicável são arquivos diferentes de propósito: a primeira carrega texto
integral, número CNJ e evidências; a segunda, só o tabulado. Ver a docstring do
exportador para o motivo.

## Conteúdo atual

| Característica | Valor |
|---|---|
| Registros | 413 |
| Atributos | 12 |
| Período | jan/2024 a jan/2026 |
| Unidades julgadoras | 22 |
| Regiões | 6 |
| Classe positiva | 67,3% |

Partições, por corte temporal: treino 250 (70,4%), calibração 81 (69,1%),
teste 82 (56,1%).

## O que fazer com os vazios em `grau_deferido`

São 217, e têm duas causas distintas que não devem ser tratadas juntas:

- **135 são estruturais** — o caso foi indeferido, e não existe grau quando o
  adicional não é reconhecido;
- **82 são falha de extração** — o caso foi deferido, o grau está escrito na
  sentença, e a regra não capturou.

Não preencher com `0`. Zero não é um grau — a NR-15 define 10, 20 e 40 —, e
`0` se confundiria com medida real, criando ordem falsa (`0 < 10 < 20 < 40`) em
qualquer modelo e distorcendo qualquer média.

A coluna `grau_ausente`, criada na versão tratada da TED 02, separa as duas
causas e torna a falha mensurável sem alterar o dado.

## Pasta irmã

`finetune/` traz o mesmo conjunto em JSONL, com o dispositivo como entrada e o
resultado como saída, em três formatos. Destina-se a ajuste de modelo de
linguagem, não ao modelo tabular.