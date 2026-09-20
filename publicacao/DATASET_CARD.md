# JuriPredict — Insalubridade / TRT-16

Conjunto de dados tabulares derivado de sentenças trabalhistas de primeiro grau
do Tribunal Regional do Trabalho da 16ª Região, com o resultado do pedido de
adicional de insalubridade rotulado.

**Versão:** 1.0 · **Gerado em:** 2026-09-19 · **Linhas:** 413

## O que este conjunto é

Uma linha por processo × pedido de adicional de insalubridade julgado no mérito
em primeiro grau. A variável-resposta `y` indica se o adicional foi deferido em
qualquer extensão.

- **Período:** 2024–2026
- **Unidades julgadoras:** 22
- **Taxa-base (y=1):** 67.3%

## O que este conjunto NÃO é

- **Não é** uma amostra de todos os processos ajuizados. A população é a dos
  pedidos que **chegaram a sentença de mérito**. Acordos homologados, extinções
  sem resolução do mérito e prescrição total do pedido ficam fora, por definição.
  Usar `y` como probabilidade de êxito ao ajuizar é erro de interpretação.
- **Não contém** texto das decisões, nome das partes, número do processo, nem
  qualquer identificador direto.
- **Não é** representativo da Justiça do Trabalho brasileira. O recorte é um
  tribunal regional.

## Colunas

| Coluna | Tipo | Valores distintos | Ausente |
|---|---|---|---|
| `id` | categórica | 413 | 0% |
| `unidade` | categórica | 22 | 0% |
| `ano` | numérica | 3 | 0% |
| `trimestre` | numérica | 4 | 0% |
| `pedido` | categórica | 1 | 0% |
| `ano_sentenca` | numérica | 3 | 0% |
| `particao` | categórica | 3 | 0% |
| `resultado_pedido` | categórica | 2 | 0% |
| `grau_deferido` | numérica | 3 | 53% |
| `y` | numérica | 2 | 0% |
| `tipo_evento` | categórica | 1 | 0% |
| `regiao` | categórica | 6 | 0% |

## Procedência

Duas fontes públicas, unidas pelo número único do processo:

- metadados processuais da base nacional do Conselho Nacional de Justiça;
- inteiro teor das sentenças no repositório oficial de jurisprudência da Justiça
  do Trabalho.

O rótulo `y` é extraído do dispositivo da sentença por regra determinística, com
os casos ambíguos encaminhados a revisão. As variáveis de conteúdo são extraídas
da fundamentação por modelo de linguagem, sobre amostra.

## Privacidade

As unidades julgadoras estão pseudonimizadas em rótulos estáveis (`unidade_01`, `unidade_02`, …). O mapeamento não é publicado.
O identificador `id` é hash truncado do número do processo: estável entre
versões, não reversível. A data foi reduzida a ano e trimestre.

Nenhuma coluna contém dado pessoal de parte, advogado ou magistrado.

## Limitações conhecidas

- **Cobertura da fonte.** Nem toda sentença proferida está indexada no
  repositório de jurisprudência. A taxa de cobertura por unidade e ano é medida
  à parte e deve ser consultada antes de comparar unidades.
- **Erro de rotulagem.** A extração automática é validada contra leitura humana
  em conjunto de referência, com concordância reportada **separadamente por
  classe de resultado**. Concordância global alta pode esconder erro que depende
  do desfecho.
- **Medição condicionada ao resultado.** Algumas variáveis de conteúdo só são
  mencionadas na sentença quando servem ao argumento vencedor. Essas estão
  marcadas e não devem ser usadas como preditoras sem validação pareada.
- **Seleção de disputas.** Casos que chegam a julgamento não são amostra
  aleatória dos ajuizados (Priest e Klein, 1984).
- **Deriva normativa.** O período pode atravessar mudanças de entendimento.
  Avaliação com divisão aleatória superestima o desempenho; use divisão temporal.

## Uso sugerido

Classificação binária com avaliação **temporal**, comparada a linhas de base de
taxa-base. Métrica primária de calibração (escore de Brier), não de acurácia.

## Citação

Sousa, E. C. *JuriPredict — Insalubridade / TRT-16*, v1.0, 2026.
