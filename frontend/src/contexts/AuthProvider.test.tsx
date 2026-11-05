import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { authService } from '../services/juripredict';
import { AuthProvider } from './AuthProvider';
import { useAuth } from './auth';

vi.mock('../services/juripredict', () => ({
  authService: { me: vi.fn(), login: vi.fn(), logout: vi.fn() },
}));

const Sair = () => {
  const { logout } = useAuth();
  return <button type="button" onClick={logout}>sair</button>;
};

describe('AuthProvider.logout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(authService.logout).mockResolvedValue(undefined);
    vi.mocked(authService.me).mockResolvedValue({ usuario: {}, memberships: [] });
  });
  afterEach(() => localStorage.clear());

  it('revoga o refresh token no servidor e limpa a sessão local', () => {
    localStorage.setItem('refresh_token', 'refresh-1');
    render(<AuthProvider><Sair /></AuthProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'sair' }));

    expect(authService.logout).toHaveBeenCalledWith('refresh-1');
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(localStorage.getItem('access_token')).toBeNull();
  });

  it('encerra a sessão local mesmo se a revogação no servidor falhar', () => {
    vi.mocked(authService.logout).mockRejectedValue(new Error('sem rede'));
    localStorage.setItem('refresh_token', 'refresh-1');
    localStorage.setItem('access_token', 'access-1');
    render(<AuthProvider><Sair /></AuthProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'sair' }));

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
  });

  it('não chama o servidor quando não há sessão para revogar', () => {
    render(<AuthProvider><Sair /></AuthProvider>);

    fireEvent.click(screen.getByRole('button', { name: 'sair' }));

    expect(authService.logout).not.toHaveBeenCalled();
  });
});
