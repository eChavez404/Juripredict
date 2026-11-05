import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import EmailVerificationBanner from '../components/auth/EmailVerificationBanner';
import { AuthContext, type AuthContextValue } from '../contexts/auth';
import { contaService } from '../features/conta/api';
import { normalizeSessao } from '../features/escritorios/sessionAdapter';
import { authService } from '../services/juripredict';
import type { Usuario } from '../types';
import ConfirmarEmail from './ConfirmarEmail';

vi.mock('../features/conta/api', () => ({
  contaService: { confirmarEmail: vi.fn(), reenviarVerificacao: vi.fn() },
}));
vi.mock('../services/juripredict', () => ({
  authService: { me: vi.fn() },
}));

const usuario: Usuario = { id: 1, username: 'm', email: 'm@x.com', nome: 'M', email_verificado: false };
const updateUser = vi.fn();

const renderCom = (page: ReactNode, user: Usuario | null, route = '/') => {
  const value = {
    user, memberships: [], capabilities: [], activeEscritorio: null, activeMembership: null,
    loading: false, login: vi.fn(), startSession: vi.fn(), updateUser, selectEscritorio: vi.fn(),
    hasCapability: () => false, logout: vi.fn(),
  } as AuthContextValue;
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthContext.Provider value={value}>{page}</AuthContext.Provider>
    </MemoryRouter>,
  );
};

describe('EmailVerificationBanner', () => {
  beforeEach(() => vi.clearAllMocks());

  it('aparece para e-mail não confirmado e reenvia o link', async () => {
    vi.mocked(contaService.reenviarVerificacao).mockResolvedValue({ detail: 'ok' });
    renderCom(<EmailVerificationBanner />, usuario);

    expect(screen.getByText(/Confirme seu e-mail \(m@x.com\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reenviar link' }));

    expect(await screen.findByText('Enviamos um novo link para o seu e-mail.')).toBeInTheDocument();
    expect(contaService.reenviarVerificacao).toHaveBeenCalledTimes(1);
  });

  it('mostra o erro quando o reenvio falha', async () => {
    vi.mocked(contaService.reenviarVerificacao).mockRejectedValue(new Error('x'));
    renderCom(<EmailVerificationBanner />, usuario);

    fireEvent.click(screen.getByRole('button', { name: 'Reenviar link' }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });

  it('não aparece com e-mail confirmado, sessão antiga ou sem usuário', () => {
    for (const user of [{ ...usuario, email_verificado: true }, { ...usuario, email_verificado: undefined }, null]) {
      const { container, unmount } = renderCom(<EmailVerificationBanner />, user);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });
});

describe('ConfirmarEmail', () => {
  beforeEach(() => vi.clearAllMocks());

  it('confirma o token do link e atualiza a sessão de quem está logado', async () => {
    vi.mocked(contaService.confirmarEmail).mockResolvedValue({ detail: 'ok' });
    vi.mocked(authService.me).mockResolvedValue({ usuario: { ...usuario, email_verificado: true } });
    renderCom(<ConfirmarEmail />, usuario, '/confirmar-email?token=abc:def');

    expect(await screen.findByText(/Seu e-mail foi confirmado/)).toBeInTheDocument();
    expect(contaService.confirmarEmail).toHaveBeenCalledWith('abc:def');
    await waitFor(() => expect(updateUser).toHaveBeenCalledWith(
      expect.objectContaining({ email_verificado: true }),
    ));
  });

  it('funciona sem login e não consulta a sessão', async () => {
    vi.mocked(contaService.confirmarEmail).mockResolvedValue({ detail: 'ok' });
    renderCom(<ConfirmarEmail />, null, '/confirmar-email?token=t');

    expect(await screen.findByText(/Seu e-mail foi confirmado/)).toBeInTheDocument();
    expect(authService.me).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Ir para o login' })).toBeInTheDocument();
  });

  it('mostra o erro do servidor quando o link é inválido', async () => {
    vi.mocked(contaService.confirmarEmail).mockRejectedValue(new Error('x'));
    renderCom(<ConfirmarEmail />, null, '/confirmar-email?token=ruim');

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText(/Seu e-mail foi confirmado/)).not.toBeInTheDocument();
  });

  it('sem token no link, avisa e nem chama o servidor', () => {
    renderCom(<ConfirmarEmail />, null, '/confirmar-email');

    expect(screen.getByText('Este link está incompleto.')).toBeInTheDocument();
    expect(contaService.confirmarEmail).not.toHaveBeenCalled();
  });
});

describe('sessão', () => {
  it('preserva email_verificado vindo do servidor (o adaptador não pode descartá-lo)', () => {
    const sessao = normalizeSessao({ usuario: { id: 1, username: 'm', email: 'm@x.com', nome: 'M', email_verificado: true } });

    expect(sessao.usuario.email_verificado).toBe(true);
  });
});
