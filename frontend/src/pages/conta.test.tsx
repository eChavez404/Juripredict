import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from '../contexts/auth';
import { contaService } from '../features/conta/api';
import AceitarConvite from './AceitarConvite';
import EsqueciSenha from './EsqueciSenha';
import RedefinirSenha from './RedefinirSenha';
import Registro from './Registro';

vi.mock('../features/conta/api', () => ({
  contaService: {
    registrar: vi.fn(),
    aceitarConvite: vi.fn(),
    solicitarReset: vi.fn(),
    confirmarReset: vi.fn(),
  },
}));

const sessao = {
  access: 'a',
  refresh: 'r',
  user: { id: 1, username: 'x', email: 'x@x.com', nome: 'X' },
};

const startSession = vi.fn();

const authValue: AuthContextValue = {
  user: null,
  memberships: [],
  capabilities: [],
  activeEscritorio: null,
  activeMembership: null,
  loading: false,
  login: vi.fn(),
  startSession,
  updateUser: vi.fn(),
  selectEscritorio: vi.fn(),
  hasCapability: () => false,
  logout: vi.fn(),
};

const renderPage = (page: ReactNode, route = '/') => render(
  <MemoryRouter initialEntries={[route]}>
    <AuthContext.Provider value={authValue}>{page}</AuthContext.Provider>
  </MemoryRouter>,
);

const digitar = (rotulo: string, valor: string) => (
  fireEvent.change(screen.getByLabelText(rotulo), { target: { value: valor } })
);

describe('cadastro', () => {
  beforeEach(() => vi.clearAllMocks());

  it('envia os dados com o aceite dos termos e abre a sessão', async () => {
    vi.mocked(contaService.registrar).mockResolvedValue(sessao);
    renderPage(<Registro />);

    digitar('Seu nome', 'Maria Souza');
    digitar('Nome do escritório', 'Souza Advocacia');
    digitar('E-mail profissional', 'maria@souza.com');
    digitar('Senha', 'uma-senha-forte-123');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /Criar conta/ }));

    await waitFor(() => expect(contaService.registrar).toHaveBeenCalledWith({
      nome: 'Maria Souza',
      escritorio_nome: 'Souza Advocacia',
      email: 'maria@souza.com',
      senha: 'uma-senha-forte-123',
      aceite_termos: true,
    }));
    expect(startSession).toHaveBeenCalledWith(sessao);
  });

  it('mostra o erro e não abre sessão quando o cadastro falha', async () => {
    vi.mocked(contaService.registrar).mockRejectedValue(new Error('falhou'));
    renderPage(<Registro />);

    digitar('Seu nome', 'Maria');
    digitar('Nome do escritório', 'Souza');
    digitar('E-mail profissional', 'maria@souza.com');
    digitar('Senha', 'uma-senha-forte-123');
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: /Criar conta/ }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(startSession).not.toHaveBeenCalled();
  });
});

describe('convite', () => {
  beforeEach(() => vi.clearAllMocks());

  it('pessoa nova envia nome, senha e o aceite dos termos', async () => {
    vi.mocked(contaService.aceitarConvite).mockResolvedValue(sessao);
    renderPage(<AceitarConvite />, '/convite?token=abc123');

    digitar('Seu nome', 'Novo Advogado');
    digitar('Crie uma senha', 'uma-senha-forte-123');
    fireEvent.click(screen.getByLabelText(/Li e aceito/));
    fireEvent.click(screen.getByRole('button', { name: 'Aceitar convite' }));

    await waitFor(() => expect(contaService.aceitarConvite).toHaveBeenCalledWith({
      token: 'abc123',
      senha: 'uma-senha-forte-123',
      nome: 'Novo Advogado',
      aceite_termos: true,
    }));
    expect(startSession).toHaveBeenCalledWith(sessao);
  });

  it('quem já tem conta envia só o token e a senha atual', async () => {
    vi.mocked(contaService.aceitarConvite).mockResolvedValue(sessao);
    renderPage(<AceitarConvite />, '/convite?token=abc123');

    fireEvent.click(screen.getByLabelText('Já tenho conta no JuriPredict'));
    expect(screen.queryByLabelText('Seu nome')).not.toBeInTheDocument();
    digitar('Senha da sua conta', 'minha-senha-atual');
    fireEvent.click(screen.getByRole('button', { name: 'Aceitar convite' }));

    await waitFor(() => expect(contaService.aceitarConvite).toHaveBeenCalledWith({
      token: 'abc123',
      senha: 'minha-senha-atual',
    }));
  });

  it('link sem token mostra o erro e não oferece o formulário', () => {
    renderPage(<AceitarConvite />, '/convite');

    expect(screen.getByRole('alert')).toHaveTextContent('incompleto');
    expect(screen.queryByRole('button', { name: 'Aceitar convite' })).not.toBeInTheDocument();
  });
});

describe('recuperação de senha', () => {
  beforeEach(() => vi.clearAllMocks());

  it('confirma o pedido sem revelar se o e-mail existe', async () => {
    vi.mocked(contaService.solicitarReset).mockResolvedValue({ detail: 'ok' });
    renderPage(<EsqueciSenha />);

    digitar('E-mail da conta', 'qualquer@x.com');
    fireEvent.click(screen.getByRole('button', { name: /Enviar link/ }));

    expect(await screen.findByText(/Se o e-mail estiver cadastrado/)).toBeInTheDocument();
    expect(contaService.solicitarReset).toHaveBeenCalledWith('qualquer@x.com');
  });

  it('não envia quando as senhas não coincidem', () => {
    renderPage(<RedefinirSenha />, '/redefinir-senha?uid=MQ&token=abc');

    digitar('Nova senha', 'uma-senha-forte-123');
    digitar('Confirmar nova senha', 'outra-senha-forte-456');
    fireEvent.click(screen.getByRole('button', { name: /Redefinir senha/ }));

    expect(screen.getByRole('alert')).toHaveTextContent('não coincidem');
    expect(contaService.confirmarReset).not.toHaveBeenCalled();
  });

  it('envia uid, token e a nova senha quando tudo confere', async () => {
    vi.mocked(contaService.confirmarReset).mockResolvedValue({ detail: 'ok' });
    renderPage(<RedefinirSenha />, '/redefinir-senha?uid=MQ&token=abc');

    digitar('Nova senha', 'uma-senha-forte-123');
    digitar('Confirmar nova senha', 'uma-senha-forte-123');
    fireEvent.click(screen.getByRole('button', { name: /Redefinir senha/ }));

    await waitFor(() => expect(contaService.confirmarReset).toHaveBeenCalledWith({
      uid: 'MQ',
      token: 'abc',
      nova_senha: 'uma-senha-forte-123',
    }));
    expect(await screen.findByText(/Senha redefinida com sucesso/)).toBeInTheDocument();
  });

  it('link sem uid ou token não oferece o formulário', () => {
    renderPage(<RedefinirSenha />, '/redefinir-senha');

    expect(screen.getByRole('alert')).toHaveTextContent('incompleto');
    expect(screen.queryByLabelText('Nova senha')).not.toBeInTheDocument();
  });
});
