# Frontend JuriPredict

Aplicação React + TypeScript construída com Vite. A interface consome a API
Django e oferece autenticação, CRUD de clientes, processos e agenda, dashboard,
jurimetria da carteira e configurações da conta.

## Execução

Com o backend ativo em `http://localhost:8000`, execute:

```powershell
cd frontend
npm ci
npm run dev
```

Acesse `http://localhost:5173`. Por padrão a interface consome
`http://localhost:8000/api/v1`. Para alterar esse endereço, copie `.env.example`
para `.env` e ajuste `VITE_API_URL`.

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
│   └── ui/          modais, feedbacks, marca, métricas e busca
├── contexts/        sessão e autenticação
├── pages/           páginas associadas às rotas
├── services/        cliente HTTP e serviços da API
├── styles/          tokens e estilos globais
├── types/           contratos TypeScript da API
└── test/            configuração do ambiente de testes
```

Os indicadores de dashboard e jurimetria não usam números demonstrativos: são
calculados a partir dos clientes, processos, resultados e compromissos do
usuário autenticado.
