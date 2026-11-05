import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { contaService } from '../../features/conta/api';
import type { TokenApi } from '../../features/conta/types';
import TokensApiPanel from './TokensApiPanel';

vi.mock('../../features/conta/api', () => ({
  contaService: { listarTokens: vi.fn(), criarToken: vi.fn(), revogarToken: vi.fn() },
}));

const token = (extra: Partial<TokenApi> = {}): TokenApi => ({
  id: 1, nome: 'Meu agente', prefixo: 'jp_abc1234', criado_em: '2026-10-01T10:00:00Z',
  expira_em: '2027-01-01T10:00:00Z', ultimo_uso_em: null, revogado_em: null, ativo: true, ...extra,
});

describe('TokensApiPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(contaService.listarTokens).mockResolvedValue([]);
  });

  it('avisa quando ainda não há tokens', async () => {
    render(<TokensApiPanel />);

    expect(await screen.findByText('Nenhum token criado.')).toBeInTheDocument();
  });

  it('lista o token só pelo prefixo, com situação e último uso', async () => {
    vi.mocked(contaService.listarTokens).mockResolvedValue([
      token(),
      token({ id: 2, nome: 'Velho', revogado_em: '2026-10-02T10:00:00Z', ativo: false }),
      token({ id: 3, nome: 'Vencido', ativo: false }),
    ]);
    render(<TokensApiPanel />);

    expect(await screen.findByText(/Meu agente/)).toBeInTheDocument();
    expect(screen.getAllByText(/jp_abc1234…/, { selector: 'small' })).toHaveLength(3);
    // o texto completo do token nunca está na lista, só o prefixo
    expect(screen.queryByText(/jp_abc1234[a-zA-Z0-9]/)).not.toBeInTheDocument();
    expect(screen.getByText(/Ativo ·.*último uso nunca/)).toBeInTheDocument();
    expect(screen.getByText(/Revogado/)).toBeInTheDocument();
    expect(screen.getByText(/Expirado/)).toBeInTheDocument();
    // só o ativo oferece revogar
    expect(screen.getAllByRole('button', { name: /Revogar token/ })).toHaveLength(1);
  });

  it('cria o token com nome, validade e senha e mostra o texto uma única vez', async () => {
    vi.mocked(contaService.criarToken).mockResolvedValue({ ...token(), token: 'jp_texto-completo-secreto' });
    render(<TokensApiPanel />);
    await screen.findByText('Nenhum token criado.');

    fireEvent.click(screen.getByRole('button', { name: /Criar token/ }));
    fireEvent.change(screen.getByLabelText(/Nome/), { target: { value: 'Meu agente' } });
    fireEvent.change(screen.getByLabelText('Validade'), { target: { value: '30' } });
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'minha-senha' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Criar token' }).at(-1)!);

    expect(await screen.findByTestId('token-criado')).toHaveTextContent('jp_texto-completo-secreto');
    expect(contaService.criarToken).toHaveBeenCalledWith({
      nome: 'Meu agente', senha: 'minha-senha', validade_dias: 30,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Já guardei' }));
    expect(screen.queryByTestId('token-criado')).not.toBeInTheDocument();
    expect(screen.queryByText('jp_texto-completo-secreto')).not.toBeInTheDocument();

    // a senha digitada não pode sobrar no formulário para a próxima abertura
    fireEvent.click(screen.getByRole('button', { name: /Criar token/ }));
    expect(screen.getByLabelText('Senha')).toHaveValue('');
    expect(screen.getByLabelText(/Nome/)).toHaveValue('');
  });

  it('mostra o erro (senha errada) sem criar nem exibir token', async () => {
    vi.mocked(contaService.criarToken).mockRejectedValue(new Error('x'));
    render(<TokensApiPanel />);
    await screen.findByText('Nenhum token criado.');

    fireEvent.click(screen.getByRole('button', { name: /Criar token/ }));
    fireEvent.change(screen.getByLabelText(/Nome/), { target: { value: 'a' } });
    fireEvent.change(screen.getByLabelText('Senha'), { target: { value: 'errada' } });
    fireEvent.click(screen.getAllByRole('button', { name: 'Criar token' }).at(-1)!);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByTestId('token-criado')).not.toBeInTheDocument();
  });

  it('revoga o token e recarrega a lista', async () => {
    vi.mocked(contaService.listarTokens)
      .mockResolvedValueOnce([token()])
      .mockResolvedValueOnce([token({ revogado_em: '2026-10-02T10:00:00Z', ativo: false })]);
    vi.mocked(contaService.revogarToken).mockResolvedValue(undefined);
    render(<TokensApiPanel />);

    fireEvent.click(await screen.findByRole('button', { name: 'Revogar token Meu agente' }));

    await waitFor(() => expect(contaService.revogarToken).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/Revogado/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Revogar token/ })).not.toBeInTheDocument();
  });

  it('mostra o erro quando a lista não carrega', async () => {
    vi.mocked(contaService.listarTokens).mockRejectedValue(new Error('x'));
    render(<TokensApiPanel />);

    expect(await screen.findByRole('alert')).toBeInTheDocument();
  });
});
