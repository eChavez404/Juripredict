# Agente JuriPredict

Agente de IA que mede um caso trabalhista, aponta o que melhorar e traz os casos mais próximos da base de decisões do TRT da 16ª Região.

## Sobre o projeto

É o agente do [JuriPredict](../README.md). Não tem tela: o advogado usa a página **Agente de IA** do app React, e só o backend Django chama este serviço, que em produção roda no mesmo contêiner do site. Tem dependências e `.env` próprios, sem acesso ao banco nem às chaves do Django. Cobre dois temas: adicional de insalubridade e adicional de periculosidade. A estrutura segue a do Treino MD Chefe.

**Situação:** estrutura pronta. A base de casos no Pinecone ainda não existe; sem ela, o agente responde só pelos critérios do tema e avisa isso na resposta.

## Como funciona

```text
React (/agente) → Django (login, papel, limite e auditoria) → agente (segredo) → Google, Pinecone, Langfuse
```

O advogado conversa com o agente na página **Agente de IA**. Ele abre um caso (tema, fase, relato, provas e, se quiser, o órgão julgador) e depois acrescenta fatos, provas e respostas às perguntas do agente. O backend guarda a conversa e, a cada mensagem, manda ao agente o caso consolidado e a mensagem nova; o agente não guarda nada. Cada análise passa por quatro etapas, orquestradas com LangGraph:

1. **Preparar o contexto:** carrega o catálogo de critérios do tema e registra as suposições.
2. **Buscar casos:** consulta no Pinecone as decisões mais parecidas com o relato.
3. **Analisar:** o modelo avalia cada critério, propõe melhorias e compara os casos. Uma resposta fora do contrato, ou que cite um caso que não veio da base, é rejeitada, com uma nova tentativa.
4. **Medir:** regras em código, sem IA, calculam o índice atual, o índice com as melhorias e o ganho possível.

### Proteção em duas camadas

| Camada | Onde | O que confere |
| ------ | ---- | ------------- |
| 1. Contrato | `schema.py` e `_validate_against_context` | **formato**: campos, tamanhos, opções, ids de critérios e de casos, na entrada e na saída |
| 2. Guard rails | `app/core/guardrails.py` | **conteúdo**: na entrada, comando dirigido à IA; na saída, fonte legal ou processo inventado, previsão de êxito, link, dado pessoal e vazamento do prompt |

As duas são código. O `guardrails.md` orienta o modelo, mas não conta como camada: ele pode descumprir. Uma resposta recusada é refeita uma vez, com o motivo; se falhar de novo, a análise não é exibida. Um caso da base com comando para a IA é descartado, com aviso.

Os guard rails não verificam se a análise jurídica está certa, nem pegam nome de pessoa ou fonte real usada fora de contexto: a revisão do advogado continua necessária.

### Quando o provedor falha

Erro passageiro do Google (5xx, 429 ou conexão) é repetido com espera crescente e, por fim, vai para o modelo reserva (`LLM_FALLBACK_MODEL`), com aviso no resultado. Falha na base de casos não derruba a análise: ela segue pelos critérios e avisa. Toda mensagem de erro traz um código que leva à linha do log.

### O que o índice mede

O índice vai de 0 a 100 e soma os pesos dos critérios: atendido vale 1, parcial vale 0,5 e ausente vale 0. O índice potencial considera atendidos os critérios em aberto que têm melhoria proposta e ainda podem ser corrigidos na fase atual do processo. **Não é probabilidade de êxito.**

Todos os prompts são Markdown, em `app/prompts/analista/`: `system.md` (papel e tarefa), `guardrails.md` (limites), `correcao.md` (nova tentativa) e `criterios/` (um arquivo por tema). Os critérios são lidos campo a campo: um erro de digitação impede o agente de subir. São um rascunho: pesos, prazos de correção e vigência dos fundamentos, marcados com `TODO(revisão)`, ainda precisam ser confirmados por um advogado.

## Tecnologias

- Python 3.11+, FastAPI e LangGraph
- LangChain com Google Gemini (modelo) e Gemini Embedding (vetores)
- Pinecone (base vetorial)
- Langfuse para observabilidade (opcional)
- uv, pytest e Ruff

## Como executar

É preciso ter o [uv](https://docs.astral.sh/uv/) instalado. A partir da raiz do repositório:

```bash
cd agente
uv sync
cp .env.example .env
uv run python -m app.main
```

Para usar pelo app, suba também o backend e o frontend, com `AGENTE_URL=http://127.0.0.1:8001` e o mesmo `AGENTE_SEGREDO` no `.env` do backend.

### Variáveis do `.env`

| Variável | Uso |
| -------- | --- |
| `AGENTE_SEGREDO` | Segredo compartilhado com o backend; sem ele, a API recusa tudo |
| `LLM_MODEL` | Modelo, no formato `provedor:modelo` (obrigatória) |
| `LLM_FALLBACK_MODEL` | Modelo reserva; vazio desliga |
| `GOOGLE_API_KEY` | Chave do Google, usada no modelo e nos embeddings |
| `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | Modelo e dimensão dos vetores; a dimensão precisa ser a do índice |
| `PINECONE_API_KEY`, `PINECONE_INDEX`, `PINECONE_NAMESPACE` | Base de casos; sem chave e índice, a busca é pulada com aviso |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Sem as duas chaves, nada é enviado |

## API

| Método | Rota | Descrição |
| ------ | ---- | --------- |
| `GET` | `/health` | Verifica se o serviço está no ar |
| `GET` | `/api/v1/options` | Lista as opções do formulário |
| `POST` | `/api/v1/analyses` | Inicia a análise e devolve um `job_id` |
| `GET` | `/api/v1/analyses/{job_id}` | Consulta o andamento e o resultado |

Fora o `/health`, tudo exige `Authorization: Bearer <AGENTE_SEGREDO>`, conferido antes de ler o corpo da requisição. Não há documentação pública da API.

Os jobs ficam na memória de um único processo: somem ao reiniciar o serviço e não funcionam com vários workers. Por padrão, o serviço só atende em `127.0.0.1`.

## Base de casos (RAG)

A busca traz os casos mais parecidos **separados por resultado**, metade deferidos e metade indeferidos, para o advogado ver o que deu certo e o que deu errado em casos como o dele. A resposta traz o que mudou, o novo índice e até cinco perguntas sobre o que falta saber.

Para criar a base no Pinecone, com as sentenças do TRT-16 já sem nomes de parte:

```bash
cd dataset/pipeline
python exportar_jurimetria.py --rag ../data/rag_trt16.jsonl   # trechos sem nome de parte
cd ../../agente
uv run python -m app.indexar ../dataset/data/rag_trt16.jsonl  # cria o índice e envia os vetores
```

O indexador cria o índice se ele não existir (768 dimensões, cosseno, AWS us-east-1) e retoma de onde parou. Usa `GOOGLE_API_KEY`, `PINECONE_API_KEY` e `PINECONE_INDEX` do `.env` do agente; depois, preencha os mesmos dois do Pinecone no Render. São cerca de 7 mil trechos de 3,2 mil sentenças.

## Contrato da base

Cada vetor no Pinecone precisa trazer os metadados de `RetrievedCase`, em `app/core/vector_store.py`: `id_sentenca` e `texto` (obrigatórios), `numero_cnj`, `tipo_documento`, `orgao_julgador`, `data_julgamento` e `resultado`, além de `temas`, uma lista com `insalubridade` e/ou `periculosidade`. Registro fora do contrato faz a busca falhar, e a análise segue sem casos, com aviso.

## Dados pessoais

- O agente recebe só o caso: nem usuário, nem escritório, nem token.
- Os dados pessoais são mascarados na entrada da API e nos trechos da base, antes de chegar ao Google e ao Langfuse (`app/core/privacy.py`):
  - pelo formato: CPF, CNPJ, PIS, e-mail, telefone e CEP;
  - pelo rótulo que os precede: RG, CTPS, OAB, CNH, título de eleitor, agência, conta e data de nascimento;
  - endereço, quando começa por um logradouro depois de "residente", "com sede" ou "endereço";
  - **nomes, só onde o texto os marca:** depois de um rótulo ("Reclamante:", "Testemunhas:"), de um título ("Dr.", "Sra.") ou antes da qualificação ("..., brasileira", "..., CPF"). Um nome solto passa; por isso o formulário pede que não sejam informados.
  - `tests/test_privacy.py` confere um contrato de trabalho inteiro (23 dados pessoais) e trechos de sentença que precisam ficar intactos, como "art. 818 da CLT c/c art. 373 do CPC".
- Os trechos da base são indexados sem os nomes das partes (`exportar_jurimetria.py`). O texto da decisão não é devolvido pela API.
- Os logs não registram relato, prompt nem resposta.

## Hospedagem

Em produção, o agente roda **no mesmo serviço do site**, como um segundo processo (`backend/iniciar.sh`). Ele só atende em `127.0.0.1`, então não tem URL pública, e o segredo é gerado a cada partida. No Render, as chaves (`GOOGLE_API_KEY` e, se usados, Pinecone e Langfuse) ficam em Environment do serviço `juripredict`.

O processo recebe só as variáveis da lista do `iniciar.sh`, sem as chaves do Django nem a do banco, e não consegue lê-las do processo do site (`gunicorn.conf.py`). É um isolamento menor que o de um contêiner próprio: os dois compartilham memória, CPU, usuário do sistema e rede.

O agente liga alguns segundos depois do site, e a página espera. Se ele cair, volta em 10 segundos; as análises em andamento se perdem.

## Testes

Os testes usam um modelo simulado e ignoram o `.env`, então não fazem chamadas reais ao Google, ao Pinecone nem ao Langfuse.

```bash
uv run pytest
```

## Estrutura

```text
app/
  agents/analista/    grafo, nós e contratos do agente
  api/v1/             endpoints da API
  core/               configuração, modelo, base vetorial, privacidade e erros
  prompts/analista/   prompts e critérios por tema, em Markdown
tests/                testes automatizados
```
