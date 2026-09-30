# Backend JuriPredict

API Django REST Framework com autenticação JWT, isolamento de dados por usuário e
CRUD de clientes, processos e compromissos. O dashboard e a jurimetria são
calculados a partir dos registros do próprio escritório.

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

Antes do primeiro acesso, crie o usuário administrador. Se já existir um usuário
e for necessário trocar a senha:

```powershell
python backend\juripredict\manage.py createsuperuser
python backend\juripredict\manage.py changepassword <usuario>
```

## Recursos da API

Todos os endpoints abaixo usam o prefixo `/api/v1/`:

```text
POST         auth/token/                autenticação por usuário ou e-mail
POST         auth/token/refresh/        renovação do JWT
GET|PATCH    auth/me/                   perfil do usuário
POST         auth/password/             alteração de senha
GET|POST     clientes/                   lista e cria clientes
GET|PUT|PATCH|DELETE clientes/{id}/      CRUD individual de cliente
GET|POST     processos/                  lista e cria processos
GET|PUT|PATCH|DELETE processos/{id}/     CRUD individual de processo
GET|POST     eventos/                    lista e cria compromissos
GET|PUT|PATCH|DELETE eventos/{id}/       CRUD individual de compromisso
GET          dashboard/                  indicadores operacionais
GET          jurimetria/                 análise descritiva da carteira
```

CPF/CNPJ é criptografado no banco e acompanhado de um hash determinístico para
impedir duplicidade. Um cliente com processos vinculados não pode ser excluído.

## Validação

Execute a partir de `backend/juripredict`:

```powershell
..\..\.venv\Scripts\python.exe manage.py check
..\..\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
..\..\.venv\Scripts\python.exe manage.py test
```

O armazenamento de arquivos é local por padrão. Para Cloudflare R2, configure
as credenciais do `.env` e defina `USE_R2_STORAGE=true`.
