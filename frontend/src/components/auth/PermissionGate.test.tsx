import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from '../../contexts/auth';
import PermissionGate from './PermissionGate';

const authValue = (capabilities: string[]): AuthContextValue => ({
  user: { id: 1, username: 'admin', email: 'admin@gmail.com', nome: 'Admin' },
  memberships: [],
  capabilities,
  activeEscritorio: null,
  activeMembership: null,
  loading: false,
  login: vi.fn(),
  updateUser: vi.fn(),
  selectEscritorio: vi.fn(),
  hasCapability: (capability) => capabilities.includes(capability),
  logout: vi.fn(),
});

describe('PermissionGate', () => {
  it('renderiza a ação quando a capability está presente', () => {
    render(
      <AuthContext.Provider value={authValue(['membros.gerenciar'])}>
        <PermissionGate capability="membros.gerenciar"><button type="button">Gerenciar</button></PermissionGate>
      </AuthContext.Provider>,
    );

    expect(screen.getByRole('button', { name: 'Gerenciar' })).toBeInTheDocument();
  });

  it('renderiza o fallback quando a capability está ausente', () => {
    render(
      <AuthContext.Provider value={authValue([])}>
        <PermissionGate capability="membros.gerenciar" fallback={<span>Somente leitura</span>}>
          <button type="button">Gerenciar</button>
        </PermissionGate>
      </AuthContext.Provider>,
    );

    expect(screen.queryByRole('button', { name: 'Gerenciar' })).not.toBeInTheDocument();
    expect(screen.getByText('Somente leitura')).toBeInTheDocument();
  });
});
