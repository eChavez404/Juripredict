# Frontend JuriPredict

Aplicação React + TypeScript construída com Vite. A interface consome a API
Django e oferece autenticação, CRUD de clientes, processos e agenda, dashboard,
jurimetria, gestão da equipe, auditoria e configurações da conta.

## Execução

Com o backend ativo em `http://localhost:8000`, execute:

```powershell
cd frontend
npm ci
npm run dev
```

Acesse `http://localhost:5173`. O Vite encaminha `/api` ao backend em
`http://localhost:8000`, mantendo frontend e API na mesma origem lógica. Para
usar uma API externa, copie `.env.example` para `.env` e ajuste `VITE_API_URL`.

Com `docker compose up --build`, acesse `http://localhost`; o Nginx do frontend
encaminha `/api/` ao contêiner do backend.

Antes do primeiro acesso, crie o administrador pelo backend. Depois disso, use
o e-mail e a senha cadastrados na tela de login.

## Comandos

```powershell
npm run dev          # servidor de desenvolvimento
npm run lint         # análise estática com Oxlint
npm test             # testes com Vitest
npm run test:watch   # testes em modo interativo
npm run build        # TypeScript + build de produção
npm run preview      # prévia do build
```

## Estrutura

```text
src/
├── components/      layout e componentes reutilizáveis
│   ├── auth/        proteção de rotas por capacidade
│   ├── settings/    componentes de configurações
│   └── ui/          modais, feedbacks, marca, métricas e busca
├── contexts/        sessão e autenticação
├── features/        regras por domínio, como seleção de escritório
├── pages/           páginas associadas às rotas
├── services/        cliente HTTP e serviços da API
├── styles/          tokens e estilos globais
├── types/           contratos TypeScript da API
└── test/            configuração do ambiente de testes
```

Os indicadores de dashboard e jurimetria não usam números demonstrativos: são
calculados a partir dos clientes, processos, resultados e compromissos do
usuário autenticado.
