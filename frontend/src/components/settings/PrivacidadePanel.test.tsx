import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from '../../contexts/auth';
import { contaService } from '../../features/conta/api';
import PrivacidadePanel from './PrivacidadePanel';

vi.mock('../../features/conta/api', () => ({
  contaService: { exportarDados: vi.fn(), excluirConta: vi.fn() },
}));

const logout = vi.fn();

const authValue: AuthContextValue = {
  user: { id: 1, username: 'ana', email: 'ana@x.com', nome: 'Ana' },
  memberships: [],
  capabilities: [],
  activeEscritorio: null,
  activeMembership: null,
  loading: false,
  login: vi.fn(),
  startSession: vi.fn(),
  updateUser: vi.fn(),
  selectEscritorio: vi.fn(),
  hasCapability: () => false,
  logout,
};

const renderPanel = () => render(
  <MemoryRouter>
    <AuthContext.Provider value={authValue}>
      <PrivacidadePanel />
    </AuthContext.Provider>
  </MemoryRouter>,
);

describe('PrivacidadePanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('baixa os dados como arquivo', async () => {
    vi.mocked(contaService.exportarDados).mockResolvedValue(new Blob(['{}']));
    const criar = vi.fn(() => 'blob:fake');
    const revogar = vi.fn();
    Object.assign(URL, { createObjectURL: criar, revokeObjectURL: revogar });
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: /Baixar meus dados/ }));

    await waitFor(() => expect(criar).toHaveBeenCalled());
    expect(revogar).toHaveBeenCalledWith('blob:fake');
  });

  it('só exclui depois de a pessoa informar a senha e então encerra a sessão', async () => {
    vi.mocked(contaService.excluirConta).mockResolvedValue(undefined);
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: /Excluir minha conta/ }));
    expect(contaService.excluirConta).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'minha-senha' } });
    fireEvent.click(screen.getByRole('button', { name: 'Excluir definitivamente' }));

    await waitFor(() => expect(contaService.excluirConta).toHaveBeenCalledWith('minha-senha'));
    expect(logout).toHaveBeenCalled();
  });

  it('mostra o motivo e mantém a sessão quando a exclusão é recusada', async () => {
    vi.mocked(contaService.excluirConta).mockRejectedValue(new Error('recusada'));
    renderPanel();

    fireEvent.click(screen.getByRole('button', { name: /Excluir minha conta/ }));
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'x' } });
    fireEvent.click(screen.getByRole('button', { name: 'Excluir definitivamente' }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(logout).not.toHaveBeenCalled();
  });
});
