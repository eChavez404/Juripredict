import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from '../contexts/auth';
import { auditoriaService } from '../features/auditoria/api';
import { equipeService } from '../features/escritorios/api';
import type { MembroResumo } from '../features/escritorios/types';
import Auditoria from './Auditoria';
import Equipe from './Equipe';

vi.mock('../features/escritorios/api', () => ({
  equipeService: { list: vi.fn(), update: vi.fn() },
}));

vi.mock('../features/auditoria/api', () => ({
  auditoriaService: { list: vi.fn() },
}));

const usuario = { id: 1, username: 'admin', email: 'admin@gmail.com', nome: 'Admin' };
const membro: MembroResumo = {
  id: 'membership-1',
  usuario,
  escritorio: {
    id: 'office-1', nome: 'Silva Advocacia', fuso_horario: 'America/Sao_Paulo',
  },
  papel: 'OWNER',
  status: 'ATIVO',
  criado_em: '',
  atualizado_em: '',
};
const capabilities = ['membros.ler', 'membros.gerenciar', 'auditoria.ler'];

const authValue: AuthContextValue = {
  user: usuario,
  memberships: [membro],
  capabilities,
  activeEscritorio: membro.escritorio,
  activeMembership: membro,
  loading: false,
  login: vi.fn(),
  updateUser: vi.fn(),
  selectEscritorio: vi.fn(),
  hasCapability: (capability) => capabilities.includes(capability),
  logout: vi.fn(),
};

const renderPage = (page: React.ReactNode, route: string) => render(
  <MemoryRouter initialEntries={[route]}>
    <AuthContext.Provider value={authValue}>{page}</AuthContext.Provider>
  </MemoryRouter>,
);

describe('governanca do escritorio', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lista membros e protege a alteracao de papel por capability', async () => {
    vi.mocked(equipeService.list).mockResolvedValue([membro]);
    vi.mocked(equipeService.update).mockResolvedValue(membro);
    renderPage(<Equipe />, '/configuracoes/equipe');

    expect(await screen.findByText('admin@gmail.com')).toBeInTheDocument();
    fireEvent.change(
      screen.getByRole('combobox', { name: 'Papel de Admin' }),
      { target: { value: 'ADMIN' } },
    );

    await waitFor(() => expect(equipeService.update).toHaveBeenCalledWith(
      'office-1',
      'membership-1',
      { papel: 'ADMIN' },
    ));
  });

  it('apresenta o estado vazio da auditoria', async () => {
    vi.mocked(auditoriaService.list).mockResolvedValue([]);
    renderPage(<Auditoria />, '/configuracoes/auditoria');

    expect(await screen.findByText('Nenhum evento registrado')).toBeInTheDocument();
  });

  it('apresenta os eventos de auditoria somente para consulta', async () => {
    vi.mocked(auditoriaService.list).mockResolvedValue([{
      id: 'audit-1',
      acao: 'MEMBRO ATUALIZADO',
      descricao: 'Papel alterado.',
      atorNome: 'Admin',
      recurso: 'Equipe',
      ocorridoEm: '2026-09-29T18:30:00-03:00',
    }]);
    renderPage(<Auditoria />, '/configuracoes/auditoria');

    expect(await screen.findByText('MEMBRO ATUALIZADO')).toBeInTheDocument();
    expect(screen.getByText('Papel alterado.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /editar/i })).not.toBeInTheDocument();
  });
});
