import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuth } from '../../contexts/auth';
import { AuthProvider } from '../../contexts/AuthProvider';
import { authService } from '../../services/juripredict';
import { resolveEscritorioAtivo } from './sessionAdapter';
import { ACTIVE_ESCRITORIO_STORAGE_KEY } from './storage';
import type { MembroResumo } from './types';

vi.mock('../../services/juripredict', () => ({
  authService: {
    login: vi.fn(),
    me: vi.fn(),
    updateMe: vi.fn(),
    changePassword: vi.fn(),
  },
}));

const usuario = { id: 1, username: 'admin', email: 'admin@gmail.com', nome: 'Admin' };
const memberships: MembroResumo[] = [
  {
    id: 'membership-1',
    usuario,
    escritorio: {
      id: 'office-1', nome: 'Silva Advocacia', fuso_horario: 'America/Sao_Paulo',
    },
    papel: 'OWNER',
    status: 'ATIVO',
    criado_em: '',
    atualizado_em: '',
  },
  {
    id: 'membership-2',
    usuario,
    escritorio: {
      id: 'office-2', nome: 'Lima Juridico', fuso_horario: 'America/Sao_Paulo',
    },
    papel: 'ADMIN',
    status: 'ATIVO',
    criado_em: '',
    atualizado_em: '',
  },
];

const SessionProbe = () => {
  const { activeEscritorio, capabilities } = useAuth();
  return <div>{activeEscritorio?.nome ?? 'Sem escritorio'} - {capabilities.join(',')}</div>;
};

describe('sessao do escritorio', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it('preserva o escritorio ativo valido e aplica suas capabilities', async () => {
    localStorage.setItem('access_token', 'access');
    localStorage.setItem(ACTIVE_ESCRITORIO_STORAGE_KEY, 'office-2');
    vi.mocked(authService.me).mockResolvedValue({
      ...usuario,
      memberships,
      escritorio_ativo: memberships[1].escritorio,
      capabilities: ['auditoria.ler'],
    });

    render(<AuthProvider><SessionProbe /></AuthProvider>);

    expect(await screen.findByText('Lima Juridico - auditoria.ler')).toBeInTheDocument();
    expect(localStorage.getItem(ACTIVE_ESCRITORIO_STORAGE_KEY)).toBe('office-2');
  });

  it('exige escolha quando ha varios vinculos e a selecao e invalida', () => {
    expect(resolveEscritorioAtivo(memberships, 'office-missing')).toBeNull();
    expect(resolveEscritorioAtivo([memberships[0]], null)?.escritorio.id).toBe('office-1');
  });

  it('encerra o carregamento depois de recuperar a sessao', async () => {
    localStorage.setItem('access_token', 'access');
    vi.mocked(authService.me).mockResolvedValue({
      ...usuario,
      memberships: [memberships[0]],
      escritorio_ativo: memberships[0].escritorio,
      capabilities: ['membros.gerenciar'],
    });

    render(<AuthProvider><SessionProbe /></AuthProvider>);

    await waitFor(() => expect(authService.me).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('Silva Advocacia - membros.gerenciar')).toBeInTheDocument();
  });
});
