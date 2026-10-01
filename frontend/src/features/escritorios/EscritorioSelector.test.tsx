import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from '../../contexts/auth';
import type { MembroResumo } from './types';
import EscritorioSelector from './EscritorioSelector';

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

describe('EscritorioSelector', () => {
  it('permite trocar entre escritorios ativos', async () => {
    const selectEscritorio = vi.fn().mockResolvedValue(undefined);
    const value: AuthContextValue = {
      user: usuario,
      memberships,
      capabilities: [],
      activeEscritorio: memberships[0].escritorio,
      activeMembership: memberships[0],
      loading: false,
      login: vi.fn(),
      updateUser: vi.fn(),
      selectEscritorio,
      hasCapability: () => false,
      logout: vi.fn(),
    };

    render(<AuthContext.Provider value={value}><EscritorioSelector /></AuthContext.Provider>);
    fireEvent.change(
      screen.getByRole('combobox', { name: /ativo/i }),
      { target: { value: 'office-2' } },
    );

    await waitFor(() => expect(selectEscritorio).toHaveBeenCalledWith('office-2'));
  });
});
