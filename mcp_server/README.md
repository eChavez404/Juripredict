# Servidor MCP do JuriPredict

Permite que um agente (Claude, Cursor, etc.) consulte os dados **de um escritório**, em modo
**somente leitura**. Ele não acessa o banco: faz as mesmas chamadas à API que o aplicativo
faz, com o acesso da própria pessoa. Por isso herda o isolamento por escritório e os limites
de requisição, e cada consulta fica registrada na auditoria.

Há dois modos:

| Modo | Para quem | Como autentica |
|---|---|---|
| **Conector remoto** (HTTP, hospedado) | o advogado, o agente do JuriPredict | OAuth 2.1: cola a URL, autoriza numa tela do app |
| **Local** (stdio) | a equipe, testes | token de API em variável de ambiente |

## Conector remoto (para o usuário final)

Endereço: **`https://juripredict-mcp.onrender.com/mcp`**

- **Claude (claude.ai ou app):** Configurações > Conectores > Adicionar conector
  personalizado, cole o endereço e clique em Conectar.
- **Claude Code:** `claude mcp add --transport http juripredict https://juripredict-mcp.onrender.com/mcp`,
  depois `/mcp` para autorizar.

O cliente abre a tela **/autorizar** do JuriPredict: a pessoa entra (se ainda não estiver
logada), vê quem pede acesso, o que ele pode ler e para qual domínio volta, escolhe o
escritório e clica em **Permitir acesso**. Para desconectar: Configurações > Acesso por
agentes > Aplicativos conectados. O fluxo do lado do servidor está em
`backend/README.md`, seção "Conector MCP remoto".

**Agente do JuriPredict (`agente/`, ainda não conectado).** É um cliente OAuth como qualquer outro:
registra-se em `/oauth/registrar` (de preferência como cliente confidencial,
`token_endpoint_auth_method: client_secret_basic`, guardando o segredo no servidor dele),
leva a pessoa a `/autorizar` com PKCE S256 e `resource` igual ao endereço acima, troca o
código em `/oauth/token`, guarda o refresh token e chama este servidor com
`Authorization: Bearer <access_token>`. O token só enxerga o escritório escolhido.

Variáveis do modo HTTP (no Render, em `render.yaml`):

| Variável | Uso |
|---|---|
| `JURIPREDICT_MCP_URL` | o próprio endereço público; ativa o modo HTTP |
| `JURIPREDICT_API_URL` | API do JuriPredict |
| `JURIPREDICT_EMISSOR` | servidor de autorização (o app) |
| `JURIPREDICT_SEGREDO_INTROSPECCAO` | o mesmo `OAUTH_SEGREDO_INTROSPECCAO` do backend |

No plano gratuito o serviço hiberna sem uso: a primeira chamada pode levar até um minuto.

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

## Modo local (stdio)

Para a equipe e para testes, o servidor roda no próprio computador.

### Instalação

```bash
cd mcp_server
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/macOS: .venv/bin/pip
```

### Configuração

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
- **Registro aberto de aplicativos.** Como pede o MCP, qualquer aplicativo pode se registrar;
  o que protege é o consentimento. Por isso a tela mostra o domínio de retorno: o nome do
  aplicativo pode imitar outro, o domínio não.
- **O token herda o papel da pessoa.** Um token de estagiário não vê o valor da causa, a
  jurimetria nem o CPF/CNPJ completo (ver a tabela de papéis no `backend/README.md`). Para um
  agente que precisa de menos, use uma conta dedicada com o papel de estagiário.
- **Sem 2FA** na plataforma hoje.
- **Um escritório por conexão.** No modo local, um por execução; no remoto, cada autorização
  escolhe um.

## Testes

```bash
.venv/Scripts/python -m unittest -q
```

Usam uma API simulada (`httpx.MockTransport`) e um cliente MCP em memória; `test_http.py`
cobre o modo HTTP com o cliente oficial do SDK (metadados, 401, audiência do token e uma
ferramenta de ponta a ponta). Para validar contra a API real, suba o backend com um banco de
teste e rode um cliente MCP contra `server.py` com as variáveis acima.
