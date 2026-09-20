# finetune/

Saída de `dataset/pipeline/gerar_finetune.py`: pares `texto → rótulo` em JSONL,
para ajustar um modelo de linguagem pequeno na tarefa de **extração**.

```bash
cd dataset/pipeline
python gerar_finetune.py --banco ../data/juripredict.db --saida ../../finetune
```

## Pré-condição

O alvo do fine-tuning **não** é prever o resultado do pedido — isso é trabalho
do modelo tabular, e ali fine-tuning não se aplica. O alvo é substituir a
chamada de API em `extrair_llm.py` por um modelo local que leia o capítulo de
fundamentação e devolva os campos estruturados.

O padrão é **destilação**: `--fonte llm` treina o modelo pequeno para imitar o
professor que já roda no pipeline — o rótulo da regra onde ela decide, e o da
anotação por modelo onde ela recusou. Isso é coerente com o alvo: o modelo local
existe para substituir a chamada de API, então imitá-la é o objetivo.

O gold set **não** entra no treino. Ele fica reservado para medir o aluno: a
partição de teste só é gerada quando existe anotação humana, porque um teste
rotulado pelo mesmo processo que gerou o treino mede o próprio ajuste, não a
qualidade da extração. Enquanto o gold set estiver vazio, `teste.jsonl` sai
vazio e o manifesto registra o motivo.

`--fonte gold` treina só na anotação humana; `--fonte regra` ignora os casos
difíceis e exige `--forcar`.

## Arquivos gerados

Três formatos dos **mesmos** exemplos, porque cada provedor consome um:

| Prefixo | Formato | Para |
|---|---|---|
| `chat_*` | `{"messages": [system, user, assistant]}` | APIs de fine-tuning |
| `alpaca_*` | `{"instruction", "input", "output"}` | LoRA local — axolotl, unsloth, peft |
| `texto_rotulo_*` | `{"texto", "rotulo", "label"}` | classificador — BERT, sklearn |

Cada um em três partições: `treino`, `validacao`, `teste`. Mais
`manifesto.json` (procedência de cada rótulo, campos cobertos, cortes) e
`DATASET_CARD.md`, gerado a cada execução — nunca escrito à mão.

`teste_*` sai **vazio** até o gold set existir. Não é falha: um teste rotulado
pelo mesmo processo que gerou o treino mede o próprio ajuste.

## Opções

```bash
python gerar_finetune.py --texto dispositivo   # padrão: de onde o rótulo saiu
python gerar_finetune.py --texto recorte       # fundamentação + dispositivo
python gerar_finetune.py --alvo estruturado    # resposta em JSON, com grau
python gerar_finetune.py --formato chat        # só um formato
```

`--texto dispositivo` é o padrão porque é do dispositivo que a regra extraiu o
rótulo. Alimentar a fundamentação junto ensina o modelo a usar sinais que o
rótulo não reflete.

A divisão vem de `dividir_dataset.py` e é **temporal**, nunca aleatória
(invariante I5).
