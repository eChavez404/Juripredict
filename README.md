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
(Maranhão), a partir de 2018.

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
scripts/ingest/     pipeline de coleta, extração e rotulagem
  coletar.py          coleta com retomada e manifesto
  cortar_secoes.py    segmentação das decisões
  rotular_por_regra.py extração de resultado
  extrair_llm.py      extração de variáveis de conteúdo
  auditoria_cobertura.py  medição de cobertura das fontes
backend/            aplicação Django e API REST
frontend/           aplicação React
docs/               documentação técnica e metodológica
dados/              não versionado
```

## Rodando localmente

```bash
git clone <url-do-repositorio>
cd juripredict

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # configure banco e chaves de API
python manage.py migrate
python manage.py runserver
```

Os scripts de ingestão rodam de forma independente da aplicação:

```bash
python scripts/ingest/cortar_secoes.py      # testes embutidos
python scripts/ingest/rotular_por_regra.py  # testes embutidos
```

## Status

| Etapa | Situação |
|---|---|
| Auditoria de cobertura das fontes | em andamento |
| Pipeline de ingestão | parcial |
| Segmentação e rotulagem por regra | implementado e testado |
| Extração de variáveis de conteúdo | previsto |
| API e interface de consulta | previsto |
| Modelo preditivo | condicionado à auditoria |

## Equipe

Elias Chaves Sousa — engenharia de dados e IA
Kauan Leite dos Santos — Extração de dados via técnicas de Web Crawling e Web Scraping

## Contexto

Projeto desenvolvido em 2026.2 no curso de Sistemas de Informação do Centro
Universitário UNIBALSAS, em Balsas — MA. A documentação técnica e metodológica
completa não é pública.

---

© 2026 Elias Chaves Sousa e Kauan Leite. Todos os direitos reservados.
