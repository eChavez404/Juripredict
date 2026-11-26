# JuriPredict

**Jurimetria trabalhista sobre dados judiciais públicos, com um agente de IA que ajuda o advogado a estruturar o caso.**

![Status](https://img.shields.io/badge/status-em%20desenvolvimento-orange)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Django](https://img.shields.io/badge/django-6.x-092E20)
![PostgreSQL](https://img.shields.io/badge/postgresql-16-336791)
![React](https://img.shields.io/badge/react-19-61DAFB)

---

## Sobre

Sentenças trabalhistas são públicas, mas não estão em forma que responda à pergunta do
advogado: como esta vara vem julgando este pedido, com base em quantos casos, e quais são eles.
O JuriPredict responde isso para o **adicional de insalubridade e o de periculosidade no TRT da
16ª Região** (Maranhão) e ajuda a estruturar o caso contra o que já deu certo e o que não deu.

## O que a aplicação faz

- **Gestão do escritório:** clientes, processos, documentos, agenda, cálculo de prazos em dias
  úteis, andamentos lidos do DataJud, central de pendências, equipe com papéis, trilha de
  auditoria, e aceite, exportação e exclusão de dados (LGPD).
- **Jurimetria do TRT-16:** taxa de deferimento do pedido por vara e por ano, sempre com o n, o
  intervalo de confiança e a cobertura da fonte, o que ficou fora da conta e as sentenças que
  sustentam cada número. A aba "Seu escritório" faz o mesmo sobre a carteira cadastrada.
- **Agente de IA:** uma conversa sobre o caso. A cada fato ou prova acrescentada, o agente avalia
  o caso contra os critérios do tema, mostra o índice e a evolução dele, aponta o que melhorar,
  pergunta o que falta e traz casos parecidos do TRT-16, deferidos e indeferidos. O caso pode ser
  vinculado a um processo do escritório, e o contrato e os demais documentos entram na análise.
- **Conector MCP:** o Claude e outros assistentes consultam os dados do escritório, somente
  leitura, autorizados por OAuth numa tela do app (`/mcp`).

## Princípios

- **Nenhum número aparece sozinho.** Toda taxa vem com o número de casos, o intervalo de
  confiança e a cobertura da fonte naquele recorte.
- **Todo número é rastreável.** Dá para abrir as decisões que originaram qualquer estimativa.
- **Quando o dado não sustenta, não se estima.** Abaixo do piso de amostra, sem a conferência
  humana do rótulo ou sem a cobertura medida, a tela informa o motivo em vez de um número frágil.
- **O índice do agente não é probabilidade de êxito.** Mede quanto do que o tema exige está
  demonstrado, e é calculado em código, não pela IA.

Dados pessoais das partes não viram variável nem aparecem na tela: os trechos de decisões saem
sem nome de parte, e documentos pessoais, contatos, endereços, dados bancários e nomes qualificados
(como num contrato) são mascarados antes de qualquer envio à IA.

## Arquitetura

Um contêiner só, em produção e no Docker local:

```text
navegador ─► nginx (porta pública)
              ├─ /mcp ─────────► servidor MCP   127.0.0.1:8002 ─┐
              └─ resto ────────► Django + React  127.0.0.1:8000 ◄┘ (API, por dentro)
                                    │
                                    └─► agente de IA  127.0.0.1:8001 ─► Google, Pinecone, Langfuse
PostgreSQL ◄── Django
```

O `backend/iniciar.sh` sobe os quatro processos; o agente e o MCP recebem só as variáveis de que
precisam, sem as chaves do Django nem a do banco, e o `manter.sh` reinicia o que cair. A base de
decisões vem de um pipeline que roda fora da aplicação (`dataset/`).

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, Django 6, Django REST Framework, Simple JWT, drf-spectacular |
| Frontend | React 19, TypeScript, Vite, Axios, Recharts |
| Agente de IA | FastAPI, LangChain, LangGraph, Gemini, Pinecone, Langfuse |
| Conector MCP | SDK oficial do MCP, OAuth 2.1 |
| Dados | coletor do Falcão (CSJT), regras de rotulagem, pandas, SQLite |
| Banco e hospedagem | PostgreSQL, Docker, Render |

## Estrutura

```text
backend/       Django: API, autenticação, escritórios, auditoria, jurimetria e conversa com o agente
frontend/      React: as telas do app
agente/        agente de IA (FastAPI + LangGraph), sem tela; só o backend o chama
mcp_server/    servidor MCP somente leitura
dataset/       coleta no Falcão e pipeline que gera a base da jurimetria e do RAG
Dockerfile     imagem única de produção (site, agente e MCP)
render.yaml    hospedagem no Render
```

## Rodando localmente

**Com Docker** (a aplicação inteira, igual à produção, com PostgreSQL):

```powershell
Copy-Item .env.example .env       # preencha as três chaves obrigatórias
docker compose up --build
```

Acesse `http://localhost:8080`. Para o agente analisar, preencha também a `GOOGLE_API_KEY`.

**Para desenvolver**, cada parte roda separada:

```powershell
# backend, em http://localhost:8000
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\juripredict\.env.example backend\juripredict\.env
python backend\juripredict\manage.py migrate
python backend\juripredict\manage.py runserver

# frontend, em http://localhost:5173 (encaminha /api ao backend)
cd frontend; npm ci; npm run dev

# agente de IA, em http://127.0.0.1:8001
cd agente; uv sync; Copy-Item .env.example .env; uv run python -m app.main
```

Para o backend falar com o agente, use o mesmo `AGENTE_SEGREDO` no `.env` dos dois e
`AGENTE_URL=http://127.0.0.1:8001` no do backend. Os detalhes estão em `backend/README.md`,
`frontend/README.md`, `agente/README.md` e `mcp_server/README.md`.

## Bases de dados: jurimetria e RAG

O corpus são sentenças públicas do TRT-16 baixadas do Falcão (`dataset/collector/`), fora do Git
por trazerem nomes de partes. O pipeline rotula o resultado de cada pedido por regra e gera duas
saídas sem nome de parte: o CSV da jurimetria e os trechos do RAG.

```bash
cd dataset/pipeline
python processar.py --entrada C:/dados/falcao-trt16/normalized --somente sentencas \
  --temas insalubridade,periculosidade --banco ../data/trt16.db \
  --manifest C:/dados/falcao-trt16/manifests/falcao.sqlite
python exportar_jurimetria.py --rag ../data/rag_trt16.jsonl

# jurimetria: importa no banco (em produção, com a DATABASE_URL externa do Render)
python ../../backend/juripredict/manage.py importar_decisoes_trt ../data/jurimetria_trt16.csv

# RAG: cria o índice no Pinecone e envia os trechos (chaves no .env do agente)
cd ../../agente && uv run python -m app.indexar ../dataset/data/rag_trt16.jsonl
```

**As taxas do TRT-16 só aparecem depois de validadas.** Até lá, a tela mostra o n e as sentenças.
Para liberar:

1. **Conferência humana:** ler e anotar uma amostra (`python gold_set.py amostrar --banco ../data/trt16.db --n 70`)
   e medir a concordância (`python gold_set.py comparar`).
2. **Cobertura:** medir com `auditoria_cobertura.py`, que precisa da chave do DataJud.
3. **Reimportar com a validação:** `importar_decisoes_trt` com `--validacao validacao.json`:

```json
{"gold_set": {"anotados": 70, "concordancia_deferido": 0.95, "concordancia_indeferido": 0.93},
 "cobertura": {"geral": 81, "Vara do Trabalho de Balsas": 84, "ano:2025": 79}}
```

As travas são `JURIMETRIA_TRT_GOLD_MINIMO` (50 decisões) e `JURIMETRIA_TRT_CONCORDANCIA_MINIMA`
(0,9 em deferidos e em indeferidos).

## Testes

```bash
cd backend/juripredict && python manage.py test        # API, papéis, jurimetria, agente
cd frontend && npm run lint && npm test && npm run build
cd agente && uv run pytest                             # grafo, guard rails, busca, indexador
cd mcp_server && python -m unittest
python -m pytest dataset/tests                         # coletor e pipeline
```

O CI (`.github/workflows/ci.yml`) roda tudo isso e constrói a imagem de produção.

## Hospedagem

Em produção: **https://juripredict.onrender.com**. O Render (`render.yaml`) publica a imagem da raiz como um serviço web, com o banco PostgreSQL e
três tarefas agendadas (lembretes, andamentos e limpeza de tokens; plano pago). No painel, em
Environment do serviço `juripredict`, ficam as chaves de fora do código: `GOOGLE_API_KEY` (agente),
`PINECONE_API_KEY` e `PINECONE_INDEX` (casos parecidos), e-mail, armazenamento R2, DataJud e Sentry.

## O que falta para abrir a clientes

- **Conferência humana do rótulo e cobertura da fonte:** sem elas, as taxas do TRT-16 ficam suprimidas.
- **Base do RAG no Pinecone:** sem ela, o agente analisa pelos critérios, sem casos parecidos.
- **Plano pago do Gemini e Política de Privacidade:** no plano gratuito, o Google pode usar o
  conteúdo enviado; a política precisa citar os provedores de IA antes do uso com casos reais.
- **Revisão jurídica dos critérios do agente**, que são um rascunho.
- **Configuração de produção:** provedor de e-mail, armazenamento em R2, plano com backup do
  banco e revisão dos Termos por um advogado (detalhes em `backend/README.md`).

## Contexto

Projeto desenvolvido em 2026.2 no curso de Sistemas de Informação do Centro Universitário
UNIBALSAS, em Balsas — MA. O material acadêmico das TEDs (notebooks, scripts e resultados de Big
Data) saiu do repositório na limpeza de novembro de 2026 e está na tag `antes-da-limpeza`.

---

© 2026 Elias Chaves Sousa e Kauan Leite. Todos os direitos reservados.
