import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { processoService } from '../../services/juripredict';
import type { AndamentosResposta, Processo } from '../../types';
import AndamentosModal from './AndamentosModal';

vi.mock('../../services/juripredict', () => ({
  processoService: { andamentos: vi.fn(), sincronizarAndamentos: vi.fn() },
  prazoService: { calcular: vi.fn() },
  eventoService: { create: vi.fn() },
}));

const processo = { id: 7, numero_cnj: '0001234-56.2023.5.16.0001' } as Processo;

const resposta = (nomes: string[], sincronizado: string | null = '2024-03-01T12:00:00Z'): AndamentosResposta => ({
  sincronizado_em: sincronizado,
  andamentos: nomes.map((nome, i) => ({
    id: i + 1, data_hora: '2024-02-01T12:00:00Z', codigo: i, nome, complemento: i === 0 ? 'tipo: sorteio' : '',
  })),
});

describe('AndamentosModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('cria prazo a partir do andamento, levando a data, o nome e o processo', async () => {
    vi.mocked(processoService.andamentos).mockResolvedValue(resposta(['Publicado acórdão']));
    render(<AndamentosModal processo={{ ...processo, area: 'TRABALHISTA' }} onClose={vi.fn()} />);

    fireEvent.click(await screen.findByRole('button', { name: /Criar prazo/ }));

    expect(await screen.findByText('Calcular prazo')).toBeInTheDocument();
    expect(screen.getByLabelText('Data')).toHaveValue('2024-02-01');
    expect(screen.queryByText('Andamentos')).not.toBeInTheDocument();
  });

  it('não consulta nada enquanto nenhum processo está selecionado', () => {
    render(<AndamentosModal processo={null} onClose={vi.fn()} />);

    expect(processoService.andamentos).not.toHaveBeenCalled();
    expect(screen.queryByText('Andamentos')).not.toBeInTheDocument();
  });

  it('lista os andamentos do processo com a data da última leitura', async () => {
    vi.mocked(processoService.andamentos).mockResolvedValue(resposta(['Distribuição', 'Audiência']));
    render(<AndamentosModal processo={processo} onClose={vi.fn()} />);

    expect(await screen.findByText('Distribuição')).toBeInTheDocument();
    expect(screen.getByText('Audiência')).toBeInTheDocument();
    expect(screen.getByText('tipo: sorteio')).toBeInTheDocument();
    expect(screen.getByText(/Última leitura em/)).toBeInTheDocument();
    expect(processoService.andamentos).toHaveBeenCalledWith(7);
  });

  it('explica o vazio, incluindo segredo de justiça, em vez de uma lista em branco', async () => {
    vi.mocked(processoService.andamentos).mockResolvedValue(resposta([], null));
    render(<AndamentosModal processo={processo} onClose={vi.fn()} />);

    expect(await screen.findByText(/segredo de justiça/)).toBeInTheDocument();
    expect(screen.getByText('Ainda não consultado.')).toBeInTheDocument();
  });

  it('atualiza pelo DataJud e informa quantos andamentos eram novos', async () => {
    vi.mocked(processoService.andamentos).mockResolvedValue(resposta([], null));
    vi.mocked(processoService.sincronizarAndamentos).mockResolvedValue({ ...resposta(['Juntada']), novos: 1 });
    render(<AndamentosModal processo={processo} onClose={vi.fn()} />);
    await screen.findByText('Ainda não consultado.');

    fireEvent.click(screen.getByRole('button', { name: /Atualizar agora/ }));

    expect(await screen.findByText('1 andamento novo.')).toBeInTheDocument();
    expect(screen.getByText('Juntada')).toBeInTheDocument();
  });

  it('diz que não há novidade quando nada mudou', async () => {
    vi.mocked(processoService.andamentos).mockResolvedValue(resposta(['A']));
    vi.mocked(processoService.sincronizarAndamentos).mockResolvedValue({ ...resposta(['A']), novos: 0 });
    render(<AndamentosModal processo={processo} onClose={vi.fn()} />);
    await screen.findByText('A');

    fireEvent.click(screen.getByRole('button', { name: /Atualizar agora/ }));

    expect(await screen.findByText('Nenhum andamento novo.')).toBeInTheDocument();
  });

  it('mantém a lista e mostra o erro quando a consulta ao DataJud falha', async () => {
    vi.mocked(processoService.andamentos).mockResolvedValue(resposta(['Antigo']));
    vi.mocked(processoService.sincronizarAndamentos).mockRejectedValue(new Error('x'));
    render(<AndamentosModal processo={processo} onClose={vi.fn()} />);
    await screen.findByText('Antigo');

    fireEvent.click(screen.getByRole('button', { name: /Atualizar agora/ }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Antigo')).toBeInTheDocument();
  });

  it('mostra o erro quando o carregamento inicial falha', async () => {
    vi.mocked(processoService.andamentos).mockRejectedValue(new Error('x'));
    render(<AndamentosModal processo={processo} onClose={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });
});
