# Servidor MCP do JuriPredict

Permite que um agente (Claude, Cursor, etc.) consulte os dados **do escritório de quem o
executa**, em modo **somente leitura**. Ele não acessa o banco: faz as mesmas chamadas à API
que o aplicativo faz, com um **token de API** da própria pessoa. Por isso herda o isolamento
por escritório e os limites de requisição, e cada consulta fica registrada na auditoria.

## Ferramentas

| Ferramenta | O que devolve |
|---|---|
| `listar_processos` | processos, com filtro por texto (CNJ, cliente, parte contrária) e situação |
| `andamentos_do_processo` | andamentos lidos do DataJud e a data da última leitura |
| `documentos_do_processo` | nome, tamanho, data e autor dos anexos (sem arquivo e sem link) |
| `agenda` | compromissos e prazos, com filtro de período |
| `jurimetria` | taxa de êxito da carteira com n e intervalo de confiança (nula abaixo do piso), geral, por vara e por ano, com filtros |
| `processos_da_jurimetria` | os processos concluídos por trás de uma taxa |
| `pendencias` | prazos vencidos, compromissos dos próximos 7 dias e andamentos recentes |
| `calcular_prazo` | vencimento em dias úteis, com a memória do cálculo; só calcula, não grava |
| `resumo_do_escritorio` | indicadores do painel |

Todas declaram `readOnlyHint`. Não existe ferramenta que crie, altere ou apague nada, e o
teste `test_nenhuma_chamada_usa_metodo_de_escrita` falha se alguma passar a usar outro método
que não GET. Listas são cortadas em 50 itens por padrão (máximo 200) e informam o total.

## Instalação

```bash
cd mcp_server
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
```

## Configuração

Variáveis de ambiente do processo que roda o servidor:

| Variável | Obrigatória | Uso |
|---|---|---|
| `JURIPREDICT_API_URL` | sim | ex.: `https://juripredict.onrender.com/api/v1` |
| `JURIPREDICT_TOKEN` | sim | token de API (`jp_...`), criado no app em Configurações > Acesso por agentes |
| `JURIPREDICT_ESCRITORIO_ID` | se a conta tiver mais de um escritório | UUID do escritório a consultar |

Exemplo para um cliente MCP (por exemplo o `.mcp.json` do Claude Code). **Não grave o token
no arquivo**: deixe o valor vir do ambiente de quem usa.

```json
{
  "mcpServers": {
    "juripredict": {
      "command": "mcp_server/.venv/Scripts/python.exe",
      "args": ["mcp_server/server.py"],
      "env": {
        "JURIPREDICT_API_URL": "https://juripredict.onrender.com/api/v1",
        "JURIPREDICT_TOKEN": "${JURIPREDICT_TOKEN}"
      }
    }
  }
}
```

## Token de API

Criado em **Configurações > Acesso por agentes**, confirmando a senha. O texto aparece uma
única vez; no banco fica só o hash. Cada pessoa tem até 5 tokens ativos, com validade de 30 a
365 dias (padrão 90), e pode revogá-los a qualquer momento. Trocar a senha ou excluir a conta
revoga todos.

O token só vale para **GET** em rotas fixas: processos (e andamentos e documentos deles),
eventos, jurimetria (e os processos que a sustentam), dashboard, pendências, cálculo de prazo e
`auth/me/`. A exportação da jurimetria fica de fora. Clientes, auditoria, exportação de dados, equipe
e o próprio gerenciamento de tokens ficam de fora, e qualquer rota nova nasce bloqueada. Quem
decide isso é o servidor (`accounts/authentication.py`), não este programa: um token
vazado não ganha poderes só por ser usado fora dele. Links assinados de arquivo também não
são entregues a tokens.

## Auditoria

Cada consulta feita com um token vira um evento no log do escritório (`token_api.leitura`),
e cada tentativa bloqueada, inclusive de processo de outro escritório, vira `token_api.negado`.
Ficam registrados: quem, qual credencial (só o prefixo), o caminho, o status e os **nomes** dos
filtros (nunca os valores: uma busca por nome de cliente não vira dado pessoal no log).
Criar e revogar tokens também é auditado, em todos os escritórios da pessoa. Proprietários e
administradores veem tudo em Configurações > Auditoria.

## Segurança: o que ele garante e o que não garante

- **Cada pessoa usa o próprio token.** O agente enxerga só o escritório dessa conta; outro
  escritório responde "Não encontrado". Foi verificado de ponta a ponta contra a API real.
- **O token nunca aparece nas respostas.** Erros viram mensagens fixas, sem token, URL ou
  corpo da resposta da API.
- **O texto devolvido sai para o modelo.** Dados de processos lidos por um agente deixam o
  sistema. Isso consta na Política de Privacidade, e o escritório deve usar apenas modelos e
  provedores que aprovou.
- **Injeção de prompt.** Campos como `observacoes` e os nomes de andamentos vêm de texto
  livre. As instruções do servidor mandam tratá-los como informação, mas nenhum modelo
  garante isso. A ausência de ferramentas de escrita e a lista fixa de rotas é o que limita o dano.

## Limites conhecidos

- **Token em variável de ambiente.** É um segredo de longa duração: quem o tiver lê os dados
  do escritório até ele expirar ou ser revogado. Revogue ao menor sinal de vazamento.
- **Sem OAuth.** Para um serviço hospedado em que clientes conectem o próprio agente por um
  fluxo de autorização, o caminho é OAuth; este token cobre uso próprio e da equipe.
- **O token herda o papel da pessoa.** Um token de estagiário não vê o valor da causa, a
  jurimetria nem o CPF/CNPJ completo (ver a tabela de papéis no `backend/README.md`). Para um
  agente que precisa de menos, use uma conta dedicada com o papel de estagiário.
- **Sem 2FA** na plataforma hoje.
- **Uma conta, um escritório por processo do servidor.** Para outro escritório, outra execução.

## Testes

```bash
.venv/Scripts/python -m unittest -q
```

Usam uma API simulada (`httpx.MockTransport`) e um cliente MCP em memória. Para validar
contra a API real, suba o backend com um banco de teste e rode um cliente MCP contra
`server.py` com as variáveis acima.
