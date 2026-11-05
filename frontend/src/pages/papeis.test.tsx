import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Layout from '../components/Layout';
import { AuthContext, type AuthContextValue } from '../contexts/auth';
import {
  clienteService, dashboardService, jurimetriaService, processoService,
} from '../services/juripredict';
import type { Cliente, DashboardData, Processo } from '../types';
import Clientes from './Clientes';
import Dashboard from './Dashboard';
import Jurimetria from './Jurimetria';
import Processos from './Processos';

vi.mock('../services/juripredict', () => ({
  clienteService: { list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn() },
  processoService: { list: vi.fn(), save: vi.fn(), remove: vi.fn(), andamentos: vi.fn(), documentos: vi.fn() },
  dashboardService: { get: vi.fn() },
  jurimetriaService: { get: vi.fn() },
  authService: { me: vi.fn(), logout: vi.fn() },
}));

// o que o advogado tem e o estagiário não (espelha organizations/capabilities.py)
const RESTRITAS = [
  'processos.valores.ler', 'jurimetria.ler', 'clientes.documento.ler', 'processos.excluir', 'clientes.excluir',
];
const COMUNS = ['clientes.gerenciar', 'processos.gerenciar', 'agenda.gerenciar'];

const sessao = (capabilities: string[]) => ({
  user: { id: 1, username: 'u', email: 'u@x.com', nome: 'U' },
  memberships: [], capabilities, activeEscritorio: null, activeMembership: null, loading: false,
  login: vi.fn(), startSession: vi.fn(), updateUser: vi.fn(), selectEscritorio: vi.fn(),
  hasCapability: (c: string) => capabilities.includes(c), logout: vi.fn(),
} as AuthContextValue);

const ADVOGADO = sessao([...COMUNS, ...RESTRITAS]);
const ESTAGIARIO = sessao(COMUNS);

const renderComo = (auth: AuthContextValue, pagina: ReactNode) => render(
  <MemoryRouter><AuthContext.Provider value={auth}>{pagina}</AuthContext.Provider></MemoryRouter>,
);

const processo = {
  id: 1, numero_cnj: '0000001-00.2024.5.16.0001', titulo: '', area: 'TRABALHISTA', vara: 'V', comarca: 'C',
  cliente: 1, cliente_nome: 'Cliente', parte_contraria: 'X', status: 'ATIVO', resultado: 'PENDENTE',
  valor_causa: null, data_distribuicao: null, observacoes: '', andamentos_sincronizados_em: null,
  arquivo_peticao_inicial_url: null, criado_em: '2024-01-01T00:00:00Z', atualizado_em: '2024-01-01T00:00:00Z',
} as Processo;

const cliente = {
  id: 1, nome: 'Cliente', cpf_cnpj: '*********09', email: null, telefone: null, tipo: 'PF',
  processos_count: 0, criado_em: '2024-01-01T00:00:00Z', atualizado_em: '2024-01-01T00:00:00Z',
} as Cliente;

const painel = {
  metricas: { processos_ativos: 1, novos_clientes_mes: 0, prazos_semana: 0, audiencias_proximas: 0 },
  evolucao_processos: [], status_processos: [], prazos_semana: [], processos_recentes: [], proximos_eventos: [],
} as DashboardData;

describe('papéis na interface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(processoService.list).mockResolvedValue([processo]);
    vi.mocked(clienteService.list).mockResolvedValue([cliente]);
    vi.mocked(dashboardService.get).mockResolvedValue(painel);
    vi.mocked(jurimetriaService.get).mockResolvedValue({ insight: 'texto', total_analisados: 0 } as never);
  });

  describe('menu', () => {
    it('o advogado vê Jurimetria no menu', () => {
      renderComo(ADVOGADO, <Layout />);

      expect(screen.getByRole('button', { name: /Jurimetria/ })).toBeInTheDocument();
    });

    it('o estagiário não vê Jurimetria, mas vê o resto do menu', () => {
      renderComo(ESTAGIARIO, <Layout />);

      expect(screen.queryByRole('button', { name: /Jurimetria/ })).not.toBeInTheDocument();
      for (const nome of [/Processos/, /Clientes/, /Agenda e prazos/]) {
        expect(screen.getByRole('button', { name: nome })).toBeInTheDocument();
      }
    });
  });

  describe('jurimetria', () => {
    it('o estagiário que digita o endereço vê acesso restrito e nada é consultado', async () => {
      renderComo(ESTAGIARIO, <Jurimetria />);

      expect(await screen.findByRole('alert')).toHaveTextContent('Acesso restrito');
      expect(jurimetriaService.get).not.toHaveBeenCalled();
    });
  });

  describe('painel', () => {
    it('o estagiário carrega o painel sem chamar a jurimetria e sem o card jurimétrico', async () => {
      renderComo(ESTAGIARIO, <Dashboard />);

      expect(await screen.findByText('Processos ativos')).toBeInTheDocument();
      expect(jurimetriaService.get).not.toHaveBeenCalled();
      expect(screen.queryByText('Resumo jurimétrico')).not.toBeInTheDocument();
    });

    it('o advogado vê o card jurimétrico', async () => {
      renderComo(ADVOGADO, <Dashboard />);

      expect(await screen.findByText('Resumo jurimétrico')).toBeInTheDocument();
      expect(jurimetriaService.get).toHaveBeenCalled();
    });
  });

  describe('processos', () => {
    const abrirNovo = async () => {
      await screen.findByText(processo.numero_cnj);
      fireEvent.click(screen.getByRole('button', { name: /Novo processo/ }));
    };

    it('o advogado vê o campo de valor da causa e o botão de excluir', async () => {
      renderComo(ADVOGADO, <Processos />);
      await abrirNovo();

      expect(screen.getByLabelText('Valor da causa')).toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /Excluir processo/ }).length).toBeGreaterThan(0);
    });

    it('o estagiário não vê valor da causa nem excluir, mas continua editando', async () => {
      renderComo(ESTAGIARIO, <Processos />);
      await abrirNovo();

      expect(screen.queryByLabelText('Valor da causa')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Excluir processo/ })).not.toBeInTheDocument();
      expect(screen.getAllByRole('button', { name: /Editar processo/ }).length).toBeGreaterThan(0);
      expect(screen.getByLabelText('Número CNJ')).toBeInTheDocument();
    });
  });

  describe('clientes', () => {
    it('o advogado exclui e edita o documento', async () => {
      renderComo(ADVOGADO, <Clientes />);
      await screen.findByText('Cliente');

      expect(screen.getByRole('button', { name: 'Excluir Cliente' })).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Editar Cliente' }));
      await waitFor(() => expect(screen.getByLabelText('CPF/CNPJ')).not.toHaveAttribute('readonly'));
    });

    it('o estagiário não exclui e vê o documento só para leitura ao editar', async () => {
      renderComo(ESTAGIARIO, <Clientes />);
      await screen.findByText('Cliente');

      expect(screen.queryByRole('button', { name: 'Excluir Cliente' })).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Editar Cliente' }));
      await waitFor(() => expect(screen.getByLabelText('CPF/CNPJ')).toHaveAttribute('readonly'));
    });

    it('o estagiário digita o documento ao cadastrar um cliente novo', async () => {
      renderComo(ESTAGIARIO, <Clientes />);
      await screen.findByText('Cliente');

      fireEvent.click(screen.getByRole('button', { name: /Novo cliente/ }));

      await waitFor(() => expect(screen.getByLabelText('CPF/CNPJ')).not.toHaveAttribute('readonly'));
    });
  });
});
