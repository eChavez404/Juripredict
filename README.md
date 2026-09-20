# JuriPredict

**Jurimetria trabalhista sobre dados judiciais públicos.**

Quanto vale saber que, na vara em que seu caso tramita, o pedido que você vai
fazer é deferido em 58% das vezes — e não em 80%, como você imaginava?

![Status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/django-5.x-092E20)
![PostgreSQL](https://img.shields.io/badge/postgresql-16-336791)
![React](https://img.shields.io/badge/react-18-61DAFB)

---

## Sobre

Sentenças judiciais brasileiras são públicas. Metadados de processos também.
O que não existe é a **agregação estatística** desses dados no nível em que um
advogado precisa decidir: como esta vara, neste tipo de pedido, vem julgando.

Os sistemas oficiais respondem "quais decisões existem". O JuriPredict responde
"em que proporção esse pedido é deferido aqui, com base em quantos casos, e
quais são eles".

O recorte inicial é o **adicional de insalubridade no TRT da 16ª Região**
(Maranhão). O corpus coletado até agora cobre **janeiro de 2024 a janeiro de
2026** — 787 sentenças. A janela pretendida é maior; esta é a que existe.

## Princípios

O projeto assume três compromissos que moldam a arquitetura inteira:

- **Nenhum número aparece sozinho.** Toda taxa vem acompanhada do número de
  casos que a sustenta, do intervalo de confiança e da cobertura da fonte
  naquele recorte.
- **Todo número é rastreável.** É possível abrir a lista de decisões que
  originaram qualquer estimativa exibida.
- **Quando o dado não sustenta, não se estima.** Abaixo de um piso de amostra ou
  de cobertura, a interface informa o motivo em vez de exibir um número frágil.

Dados pessoais das partes não são usados como variável nem exibidos.

## Como funciona

O sistema tem dois fluxos que rodam em momentos diferentes e não compartilham
ciclo de execução.

**Ingestão (offline, em lote).** Coleta metadados processuais e o inteiro teor
das sentenças em fontes públicas, une as duas bases pelo número CNJ, deduplica,
segmenta os documentos e extrai o resultado de cada pedido. Roda como scripts
versionados, não como serviço.

**Consulta (online).** Aplicação Django expondo API REST sobre a base já
construída, consumida por um front-end React. As consultas da primeira versão
são agregações relacionais — sem dependência de modelo em tempo de requisição.

Uma camada preditiva está prevista, isolada em serviço próprio, e só entra
depois que a qualidade da base for medida.

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3 |
| Ingestão | requests, BeautifulSoup, pandas |
| Extração | expressões regulares e modelo de linguagem via API |
| Banco de dados | PostgreSQL |
| Backend | Django, Django REST Framework |
| Frontend | React |
| Modelagem preditiva | scikit-learn, LightGBM *(previsto)* |
| Serviço de inferência | FastAPI *(previsto)* |

## Estrutura

```
dataset/
  collector/        coleta no repositório de jurisprudência
    session.py        sessão pública, com alternativa manual
    client.py         limite de requisições, repetição, tamanho de página fixo
    collector.py      paginação e retomada
    storage.py        bruto + manifesto SQLite + hash
    normalize.py      HTML → texto
    audit.py          duplicidade e composição do corpus
  pipeline/         bruto → dataset rotulado
    processar.py        espinha: seções → rótulo → banco
    cortar_secoes.py    relatório / fundamentação / dispositivo
    rotular_por_regra.py extração de resultado
    extrair_llm.py      extração de variáveis de conteúdo
    gold_set.py         amostragem e concordância contra leitura humana
    rotular_ambiguos.py resolve por leitura o que a regra recusou
    montar_dataset.py   monta O dataset: invariantes, limpeza, partição
    dividir_dataset.py  confere o corte temporal 60/20/20
    exportar_dataset.py versão publicável
    gerar_finetune.py   pares texto → rótulo
    auditoria_cobertura.py  medição de cobertura das fontes
    schema.sql
  tests/            21 testes, sem rede
  data/             corpus, manifesto, banco e juripredict.csv — não versionado
publicacao/         produto: CSV publicável + cartão do conjunto
finetune/           produto: JSONL de extração
backend/            aplicação Django e API REST — camada 3, não iniciada
frontend/           aplicação React — camada 4, não iniciada
```

## Rodando localmente

```bash
git clone <url-do-repositorio>
cd juripredict

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # configure as chaves de API
```

A aplicação Django ainda não existe — ver `backend/README.md` para a
pré-condição. Hoje o que roda é a camada de dados.

**Coleta** (a partir de `dataset/`):

```bash
python -m collector.falcao --query "insalubridade" --tribunal TRT16 \
  --date-start 2024-01-01 --date-end 2026-08-18 --pages 5
```

**Pipeline** (a partir de `dataset/pipeline/`, que é o diretório de trabalho
assumido pelos caminhos padrão):

```bash
python processar.py                      # normalizado → seções → rótulo → banco
python rotular_ambiguos.py exportar      # planilha dos casos que a regra recusou
python rotular_ambiguos.py importar --aplicar
python gold_set.py amostrar --n 50       # sorteia a amostra de anotação manual
python gold_set.py comparar              # concordância, reportada por classe
python montar_dataset.py                 # grava ../data/juripredict.csv
python dividir_dataset.py                # confere o corte temporal
python exportar_dataset.py               # versão publicável + cartão
python gerar_finetune.py                 # pares texto → rótulo, por destilação
```

Todo script aceita `--demo`, que roda o caminho de código inteiro com dados
fabricados, sem rede e sem tocar no corpus:

```bash
python cortar_secoes.py                  # testes embutidos
python rotular_por_regra.py              # testes embutidos
python dividir_dataset.py --demo
cd ../ && python -m pytest tests/ -q     # 21 testes
```

## O dataset

Um arquivo: `dataset/data/juripredict.csv` — 618 linhas. Todo caso do pedido
está nele, inclusive os que não entram no modelo. Duas colunas dizem o estatuto
de cada linha, em vez de a exclusão existir só como número num relatório.

| `populacao` | linhas | o que é |
|---|---|---|
| `modelo` | 413 | sentença de mérito de 1º grau com resultado deferido ou indeferido. Único recorte treinável; só aqui `y` e `particao` estão preenchidos |
| `fora_da_populacao` | 116 | o documento não julga o pedido pela primeira vez: liquidação, embargos de declaração, homologação |
| `escape` | 89 | o pedido não foi julgado no mérito: ambíguo, não analisado, ou só mencionado de passagem |

`motivo_fora` traz o motivo exato. Para treinar ou avaliar, filtre
`populacao == "modelo"` — as demais linhas têm `y` nulo de propósito.

Taxa-base 67,3%, 22 unidades julgadoras, 7 regiões, jan/2024 a jan/2026.
Partição temporal: treino 250, calibração 81, teste 82.

### Versão do dataset

O pipeline tem duas versões, na constante `VERSAO_DATASET` em
`dataset/pipeline/rotular_por_regra.py`:

- **1.0** (ativa) — reproduz a metodologia da monografia.
- **2.0** — aplica três correções de coerência encontradas em revisão: exclui
  ações coletivas, casos em que o adicional só aparece como base de reflexo de
  outra verba, e casos em que o próprio pedido foi extinto sem mérito. Dá 396
  registros e taxa-base 68,2%.

As regras das duas versões estão escritas e testadas. `JURIPREDICT_VERSAO=2.0`
troca sem alterar código.

## Andamento

**Funciona hoje:** a camada de dados inteira. Coleta, segmentação, rotulagem por
regra, resolução dos casos ambíguos, montagem, divisão temporal, exportação
publicável e geração dos pares de fine-tuning. Tudo roda de ponta a ponta sobre
787 sentenças reais e produz o dataset acima.

**Bloqueio principal: o gold set está vazio.** Nenhum rótulo foi conferido
contra leitura humana — 89% vêm de regra determinística e 11% de leitura por
modelo. Sem essa medição não se sabe se o erro de rotulagem depende do desfecho,
que é justamente o modo de falha que o projeto existe para evitar. A amostra já
está sorteada e estratificada em `dataset/data/gold_set.csv`: 70 casos, sem o
rótulo automático à vista. É trabalho humano, e é o próximo passo.

**Cobertura ainda não medida.** O coletor do DataJud agora roda contra a API, e a
auditoria já produziu uma amostra. Mas o assunto "Adicional de Insalubridade" do
CNJ cobre só 45% das sentenças que efetivamente julgam o tema — o catálogo do
tribunal não delimita o universo, então o denominador da cobertura precisa ser
redefinido antes de o número significar alguma coisa.

| Etapa | Situação |
|---|---|
| Coleta no repositório de jurisprudência | 787 sentenças, jan/2024 a jan/2026 |
| Segmentação e rotulagem por regra | implementado, 14 casos de teste |
| Resolução dos casos ambíguos | 154 lidos e rotulados por modelo |
| Dataset consolidado | 618 linhas, 413 treináveis |
| Versão publicável | 413 linhas, pseudonimizada, sem texto |
| Pares de fine-tuning | 331 exemplos em 3 formatos |
| Gold set (anotação humana) | **vazio — bloqueia a medição de erro** |
| Auditoria de cobertura | amostra coletada, denominador em revisão |
| Extração de variáveis de conteúdo | previsto, depende do gold set |
| API e interface de consulta | não iniciadas |
| Modelo preditivo | condicionado à medição de erro |

**O que o dataset sustenta hoje:** desenvolvimento do pipeline e jurimetria
descritiva com ressalva. **O que não sustenta:** afirmar que uma vara defere
mais que outra — para isso falta medir o erro de rotulagem e a cobertura.

## Contexto

Projeto desenvolvido em 2026.2 no curso de Sistemas de Informação do Centro
Universitário UNIBALSAS, em Balsas — MA. A documentação técnica e metodológica
completa não é pública.

---

© 2026 Elias Chaves Sousa e Kauan Leite. Todos os direitos reservados.
