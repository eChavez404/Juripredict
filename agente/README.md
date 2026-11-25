# Agente JuriPredict

Agente de IA que mede um caso trabalhista, aponta o que melhorar e traz os casos mais próximos da base de decisões do TRT da 16ª Região.

## Sobre o projeto

É o agente do [JuriPredict](../README.md). Não tem tela: o advogado usa a página **Agente de IA** do app React, e só o backend Django chama este serviço. Tem dependências e `.env` próprios, sem acesso ao banco nem às chaves do Django. Cobre dois temas: adicional de insalubridade e adicional de periculosidade. A estrutura segue a do Treino MD Chefe.

**Situação:** estrutura pronta. A base de casos no Pinecone ainda não existe; sem ela, o agente responde só pelos critérios do tema e avisa isso na resposta.

## Como funciona

```text
React (/agente) → Django (login, papel, limite e auditoria) → agente (segredo) → Google, Pinecone, Langfuse
```

O advogado informa tema, fase do processo, relato, provas e, se quiser, o órgão julgador e o ponto que mais preocupa. A análise passa por quatro etapas, orquestradas com LangGraph:

1. **Preparar o contexto:** carrega o catálogo de critérios do tema e registra as suposições.
2. **Buscar casos:** consulta no Pinecone as decisões mais parecidas com o relato.
3. **Analisar:** o modelo avalia cada critério, propõe melhorias e compara os casos. Uma resposta fora do contrato, ou que cite um caso que não veio da base, é rejeitada, com uma nova tentativa.
4. **Medir:** regras em código, sem IA, calculam o índice atual, o índice com as melhorias e o ganho possível.

### O que o índice mede

O índice vai de 0 a 100 e soma os pesos dos critérios: atendido vale 1, parcial vale 0,5 e ausente vale 0. O índice potencial considera atendidos os critérios em aberto que têm melhoria proposta e ainda podem ser corrigidos na fase atual do processo. **Não é probabilidade de êxito.**

Os critérios ficam em `app/prompts/analista/criterios/`. São um rascunho: pesos, prazos de correção e vigência dos fundamentos, marcados com `TODO(revisão)`, ainda precisam ser confirmados por um advogado.

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

## Contrato da base (provisório)

Cada vetor no Pinecone precisa trazer os metadados de `RetrievedCase`, em `app/core/vector_store.py`: `id_sentenca` e `texto` (obrigatórios), `numero_cnj`, `tipo_documento`, `orgao_julgador`, `data_julgamento` e `resultado`, além de `temas`, uma lista com `insalubridade` e/ou `periculosidade`. Registro fora do contrato interrompe a busca com erro.

## Dados pessoais

- O agente recebe só o caso: nem usuário, nem escritório, nem token.
- CPF e CNPJ são mascarados na entrada da API e nos trechos da base, antes de chegar ao Google e ao Langfuse. **Nomes não são mascarados:** o formulário pede que não sejam informados.
- Os trechos da base precisam ser indexados sem os nomes das partes. O texto da decisão não é devolvido pela API.
- Os logs não registram relato, prompt nem resposta.

## Hospedagem (Render)

O `render.yaml` da raiz declara o serviço `juripredict-agente`, no plano gratuito, a partir do `Dockerfile` desta pasta. O `AGENTE_SEGREDO` é gerado no serviço `juripredict` e copiado para cá. As chaves do Google, do Pinecone e do Langfuse são preenchidas à mão no painel, em Environment.

No plano gratuito, o serviço tem URL pública (não recebe tráfego da rede privada) e hiberna após 15 minutos sem uso. A página do app percebe a hibernação, avisa e espera o agente voltar. Um reinício apaga as análises em andamento.

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
  prompts/analista/   prompt do sistema e critérios por tema
tests/                testes automatizados
```
