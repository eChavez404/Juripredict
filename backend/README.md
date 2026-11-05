# Backend JuriPredict

API Django REST Framework com autenticação JWT, isolamento por escritório,
controle de acesso por papel e trilha de auditoria. Inclui CRUD de clientes,
processos, compromissos e membros. Dashboard e jurimetria são calculados somente
a partir dos registros do escritório ativo.

## Execução local com SQLite

Na raiz do repositório, em PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
Copy-Item backend\juripredict\.env.example backend\juripredict\.env
python backend\juripredict\manage.py migrate
python backend\juripredict\manage.py runserver
```

Para usar SQLite, mantenha `DB_HOST` comentado no `.env`. Para PostgreSQL,
descomente a variável e informe as credenciais correspondentes.

Quem usa o sistema cria a própria conta em `/registro` (ou entra por convite).
O `createsuperuser` fica para a administração do Django (`/admin/`):

```powershell
python backend\juripredict\manage.py createsuperuser
python backend\juripredict\manage.py changepassword <usuario>
```

## Recursos da API

A especificação OpenAPI 3 completa, com corpos e respostas, está em
[`backend/openapi.yaml`](openapi.yaml), que pode ser importada no Postman ou no Insomnia.
Com `DJANGO_DEBUG=true`, o Swagger UI fica em `/api/docs/` e o esquema em `/api/schema/`;
em produção essas rotas não existem. Depois de mudar a API, regenere o arquivo (o teste
`api.test_openapi` falha se ele ficar defasado), a partir de `backend/juripredict`:

```powershell
python manage.py spectacular --validate --fail-on-warn --file ..\openapi.yaml
```

Todos os endpoints abaixo usam o prefixo `/api/v1/`:

```text
POST         auth/register/             cria conta, escritório e proprietário
POST         auth/token/                autenticação por usuário ou e-mail
POST         auth/token/refresh/        renovação (emite novo refresh e invalida o anterior)
POST         auth/logout/               revoga o refresh token no servidor
GET|PATCH    auth/me/                   perfil do usuário
POST         auth/password/             alteração de senha
GET|POST     auth/tokens/               lista e cria tokens de API (exige sessão e a senha)
DELETE       auth/tokens/{id}/          revoga um token de API
POST         auth/email/confirmar/      confirma o e-mail com o link recebido
POST         auth/email/reenviar/       reenvia o link de confirmação (exige login)
POST         auth/password/reset/       pede o link de recuperação por e-mail
POST         auth/password/reset/confirm/ define a nova senha com o link
POST         auth/convites/aceitar/     aceita convite (cria a conta ou vincula a existente)
GET          auth/me/exportar/          cópia dos dados da pessoa (LGPD)
POST         auth/me/excluir/           anonimiza a conta, com confirmação de senha
GET|POST     clientes/                   lista e cria clientes
GET|PUT|PATCH|DELETE clientes/{id}/      CRUD individual de cliente
GET|POST     processos/                  lista e cria processos
GET|PUT|PATCH|DELETE processos/{id}/     CRUD individual de processo
GET|POST     processos/{id}/documentos/ lista e anexa documentos (PDF, DOC, DOCX)
DELETE       processos/{id}/documentos/{doc}/  exclui o documento e o arquivo
GET          processos/{id}/andamentos/ andamentos já lidos do DataJud
POST         processos/{id}/andamentos/sincronizar/  lê o DataJud agora (30/hora)
GET|POST     eventos/                    lista e cria compromissos
GET|PUT|PATCH|DELETE eventos/{id}/       CRUD individual de compromisso
GET          dashboard/                  indicadores operacionais
GET          jurimetria/                 análise descritiva da carteira (filtros: area, ano)
GET          jurimetria/processos/       processos que sustentam uma taxa (vara, area, ano, resultado)
GET          jurimetria/exportar/        relatório CSV da análise, registrado na auditoria
GET          pendencias/                 prazos vencidos, próximos 7 dias e andamentos recentes
GET          prazos/calcular/            vencimento em dias úteis, com a memória do cálculo
GET|PATCH    escritorios/{id}/           consulta e atualização do escritório
GET          escritorios/{id}/membros/   lista da equipe
PATCH        escritorios/{id}/membros/{membro_id}/ alteração de papel/status
GET|POST     escritorios/{id}/convites/  lista e envia convites de equipe
DELETE       escritorios/{id}/convites/{convite_id}/ revoga um convite pendente
GET          auditoria/                  trilha de auditoria imutável
```

Quando o usuário pertence a mais de um escritório, envie o UUID selecionado no
header `X-Escritorio-ID`. A resposta de `auth/me/` informa memberships,
escritório ativo e capacidades efetivas.

CPF/CNPJ é criptografado no banco e acompanhado de um hash determinístico para
impedir duplicidade. Um cliente com processos vinculados não pode ser excluído.

## Entrada de clientes

- **Cadastro** (`auth/register/`): cria usuário, escritório e vínculo de proprietário numa
  transação, grava o aceite da versão vigente dos termos (`TERMOS_VERSAO`) e devolve os
  tokens, para o app entrar direto.
- **Convite**: gestores convidam por e-mail (ADMIN, ADVOGADO ou ESTAGIARIO; proprietário não
  se concede por convite). O link vale `CONVITE_VALIDADE_DIAS`, é de uso único e só o hash
  dele fica no banco. Quem já tem conta confirma com a senha atual.
- **Recuperação de senha**: a resposta é a mesma exista ou não o e-mail. O link vale
  `PASSWORD_RESET_TIMEOUT` segundos, é de uso único e derruba as sessões abertas.
- **Verificação de e-mail**: o cadastro envia um link assinado (`django.core.signing`, vale
  `VERIFICACAO_EMAIL_HORAS`, preso ao e-mail da conta). `auth/me/` expõe `email_verificado` e
  o app mostra um aviso até a confirmação; trocar o e-mail exige nova confirmação. **O login não é bloqueado**: sem SMTP isso trancaria
  todos para fora (suposição a rever quando o e-mail estiver configurado). Quem aceita
  convite já nasce verificado, pois o link chegou pela caixa de e-mail.

Os quatro dependem de e-mail. **Sem `EMAIL_HOST` nenhuma mensagem sai**: em produção o
sistema avisa no log e segue, e a recuperação de senha responde "enviado" sem enviar.

## Tarefas agendadas

O sistema não tem fila nem agendador próprio. Três comandos precisam ser chamados por
um agendador externo (cron do servidor, Render Cron Job, GitHub Actions com acesso ao banco):

```text
python manage.py enviar_lembretes      de hora em hora   prazos e audiências das próximas 24h
python manage.py sincronizar_andamentos uma vez por dia   lê os andamentos dos processos ativos no DataJud
python manage.py flushexpiredtokens    uma vez por dia   limpa refresh tokens vencidos
```

No Render, o `render.yaml` já declara os três como Cron Jobs (`juripredict-lembretes`,
`juripredict-andamentos`, `juripredict-limpeza-tokens`). Cron Job não existe no plano
gratuito: cada um custa o mínimo do plano starter. Eles copiam do serviço web os segredos
(e-mail, chaves, DataJud) e usam `FRONTEND_URL` para montar os links dos e-mails.

`enviar_lembretes` marca cada compromisso depois de enviar, então rodar a mais não repete
o aviso, e uma falha de envio é refeita na execução seguinte. Remarcar o compromisso libera
um novo lembrete.

## Papéis e o que cada um vê

A tabela única fica em `organizations/capabilities.py` e vale para a API inteira (e, por isso,
para tokens de API, que herdam o papel). O frontend usa as mesmas capabilities só para
esconder o que a pessoa não pode usar; quem decide é o servidor.

| Capability | Estagiário | Advogado | Admin / Proprietário |
|---|---|---|---|
| ler e editar processos, clientes e agenda; anexar documentos | sim | sim | sim |
| `processos.valores.ler` (valor da causa; sem ela vem nulo e não é gravado) | não | sim | sim |
| `jurimetria.ler` (a rota responde 403) | não | sim | sim |
| `clientes.documento.ler` (sem ela o CPF/CNPJ vem mascarado e não é alterado) | não | sim | sim |
| `processos.excluir` e `clientes.excluir` (403) | não | sim | sim |
| `membros.gerenciar`, `escritorio.editar`, `auditoria.ler` | não | não | sim |

As regras do estagiário são um padrão conservador: para mudar, edite a tabela.

## Tokens de API e auditoria de agentes

Credencial separada da senha para agentes (servidor MCP em `mcp_server/`). Só o hash SHA-256
fica no banco; vale `API_TOKEN_VALIDADE_DIAS` (90 por padrão, até 365), até
`API_TOKEN_MAX_ATIVOS` (5) por pessoa, e criar exige a senha. Trocar a senha, por qualquer
caminho, e excluir a conta revogam todos.

`accounts/authentication.py` é o único ponto que decide o que o token faz: só `GET`, só nas
rotas da lista `ROTAS_PERMITIDAS` (processos, andamentos, documentos, eventos, jurimetria,
dashboard, pendências, cálculo de prazo, `auth/me/`). Rota nova nasce bloqueada. O gerenciamento de tokens aceita apenas
sessão de pessoa (JWT). Para tokens, os links assinados de arquivo vêm nulos.

`accounts/middleware.py` grava no log do escritório cada consulta (`token_api.leitura`) e
cada tentativa bloqueada (`token_api.negado`), com credencial (prefixo), caminho, status e os
nomes dos filtros, nunca os valores. Sem escritório válido no cabeçalho não há onde gravar:
fica um aviso no log da aplicação. Uma falha ao auditar não derruba a resposta.

## Documentos do processo

Cada processo aceita até `DOCUMENTOS_MAX_POR_PROCESSO` anexos (50). O conteúdo é validado
como na petição inicial (tamanho, extensão e assinatura do arquivo). Excluir o documento, ou
o processo inteiro, apaga também o arquivo do storage, depois do commit da transação; o mesmo
vale para a petição inicial, inclusive quando é substituída. Envio e exclusão entram na auditoria. Ainda não há cota de espaço por escritório.

## Andamentos (DataJud)

O número CNJ diz o tribunal (`J.TR`), então não há o que configurar por escritório. Cobre a
Justiça do Trabalho (TRTs) e a Federal (TRFs); outros ramos respondem 400 com a explicação.
Exige `DATAJUD_API_KEY` (chave pública da wiki do CNJ); sem ela a consulta responde 503 e o
resto do sistema segue normal. Cada movimento é gravado uma vez (identidade: processo, data,
código e nome), então ler de novo não duplica. Processos em segredo de justiça não aparecem
no DataJud. Só o número do processo (dado público) sai para o CNJ.

A rodada diária avisa por e-mail quem cadastrou o processo, num só e-mail por escritório e
só se ele ainda for membro ativo. Na primeira leitura de um processo não há aviso (o
histórico inteiro não é novidade). A leitura manual, pelo botão, não envia e-mail.

Limite conhecido: o DataJud costuma atrasar dias em relação ao tribunal.

## Cálculo de prazos

`api/prazos.py` conta em dias úteis, excluindo o dia do começo e incluindo o do vencimento
(CLT, arts. 775 e 775-A; CPC, arts. 216, 219, 220 e 224; Lei 11.419/2006, art. 4º; TST, Súmulas
1 e 262). Atende as áreas trabalhista e cível; as demais respondem 400, porque têm contagem
própria (no penal, por exemplo, o prazo é contínuo).

A regra de desenho é **errar para antes, nunca para depois**. Só deixa de contar o que é certo:
fim de semana, feriado nacional em lei e a suspensão de 20/12 a 20/1. Carnaval, Semana Santa,
Corpus Christi e pontos facultativos dependem de ato de cada tribunal: contam como úteis e voltam
em `dias_a_conferir`, para a pessoa conferir e informar em `suspensoes`. Como o resultado é apoio
e não a data oficial, a resposta sempre traz fundamento, memória e ressalvas. Não há calendário
de tribunal gravado no sistema; quando houver, ele alimenta `suspensoes`.

## Antes de abrir para clientes

| Configuração | Sem ela |
|---|---|
| `EMAIL_HOST` e credenciais | convite, recuperação de senha e lembretes não chegam |
| `USE_R2_STORAGE=true` com as credenciais | petições enviadas somem a cada deploy |
| Plano pago com backup do banco | banco de teste pode expirar e não há cópia |
| `NUM_PROXIES` (1 no Render e no Fly) | o limite de requisições enxerga todos como um só IP |
| `SENTRY_DSN` (opcional) | erros em produção passam despercebidos |
| agendador dos dois comandos acima | sem lembretes, e a lista de tokens só cresce |

## Validação

Execute a partir de `backend/juripredict`. O `manage.py test` cria o banco de teste no
servidor configurado: se o `.env` apontar para um banco real (`SUPABASE_DB_*` ou `DB_HOST`),
defina antes `DATABASE_URL` para um PostgreSQL descartável.

```powershell
..\..\.venv\Scripts\python.exe manage.py check
..\..\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
..\..\.venv\Scripts\python.exe manage.py test
```

O armazenamento de arquivos é local por padrão. Para Cloudflare R2, configure
as credenciais do `.env` e defina `USE_R2_STORAGE=true`.

## Rotação da chave de dados pessoais

`FIELD_ENCRYPTION_KEY` cifra e gera o hash dos documentos dos clientes. Ela não
pode ser alterada diretamente. Para rotacioná-la de forma transacional, defina a
nova chave em `FIELD_ENCRYPTION_KEY`, a anterior em
`OLD_FIELD_ENCRYPTION_KEY` e execute primeiro a validação:

```powershell
python manage.py rotate_field_encryption_key --dry-run
python manage.py rotate_field_encryption_key
```

O comando interrompe toda a operação se qualquer registro não puder ser
decifrado e nunca imprime o documento nem as chaves.

## Limites de requisição

Os endpoints públicos têm limite próprio (`REST_FRAMEWORK.DEFAULT_THROTTLE_RATES`). O login
é limitado por IP e também por conta (`login_conta`), para que um ataque distribuído contra
uma senha esbarre no teto de onde quer que venha. O limite usa o cache em memória do
processo: com `WEB_CONCURRENCY=2` ele vale por worker, na prática o dobro. Para um limite
global exato, configure um cache compartilhado (Redis).
