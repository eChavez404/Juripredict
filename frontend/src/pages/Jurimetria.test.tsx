import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from '../contexts/auth';
import { jurimetriaService } from '../services/juripredict';
import type { JurimetriaData } from '../types';
import Jurimetria from './Jurimetria';

vi.mock('../services/juripredict', () => ({
  jurimetriaService: { get: vi.fn(), processos: vi.fn(), exportar: vi.fn() },
}));

const base: JurimetriaData = {
  total_analisados: 0,
  taxa_favoravel: null,
  intervalo_favoravel: null,
  amostra_suficiente: false,
  piso_amostra: 10,
  processos_ativos: 3,
  por_vara: [],
  por_ano: [],
  filtros: { area: null, ano: null },
  opcoes: { areas: [{ valor: 'CIVEL', rotulo: 'Cível' }], anos: [2025, 2024] },
  resultados: [
    { name: 'Favoráveis', value: 0 },
    { name: 'Acordos', value: 0 },
    { name: 'Desfavoráveis', value: 0 },
  ],
  insight: 'texto do insight',
};

const comCapability = {
  user: null, memberships: [], capabilities: ['jurimetria.ler'], activeEscritorio: null,
  activeMembership: null, loading: false, login: vi.fn(), startSession: vi.fn(), updateUser: vi.fn(),
  selectEscritorio: vi.fn(), hasCapability: (c: string) => c === 'jurimetria.ler', logout: vi.fn(),
} as AuthContextValue;

const renderPage = (dados: JurimetriaData) => {
  vi.mocked(jurimetriaService.get).mockResolvedValue(dados);
  return render(
    <MemoryRouter>
      <AuthContext.Provider value={comCapability}><Jurimetria /></AuthContext.Provider>
    </MemoryRouter>,
  );
};

describe('Jurimetria', () => {
  beforeEach(() => vi.clearAllMocks());

  it('não exibe percentual quando a amostra é insuficiente e diz o motivo', async () => {
    renderPage({
      ...base,
      total_analisados: 1,
      por_vara: [{
        vara: '1ª Vara', total: 1, suficiente: false,
        favoravel: null, desfavoravel: null, intervalo_favoravel: null, motivo: 'x',
      }],
    });

    expect(await screen.findByText('—')).toBeInTheDocument();
    expect(screen.getByText(/Amostra insuficiente para uma taxa \(mínimo de 10 processos\)/)).toBeInTheDocument();
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
  });

  it('mostra a taxa junto do intervalo de confiança quando há amostra', async () => {
    renderPage({
      ...base,
      total_analisados: 20,
      taxa_favoravel: 60,
      intervalo_favoravel: { min: 39, max: 78 },
      amostra_suficiente: true,
    });

    expect(await screen.findByText('60%')).toBeInTheDocument();
    expect(screen.getByText(/IC 95%: 39% a 78%/)).toBeInTheDocument();
  });

  it('lista a vara sem amostra com o n, em vez de escondê-la ou mostrar barra vazia', async () => {
    renderPage({
      ...base,
      total_analisados: 12,
      taxa_favoravel: 50,
      intervalo_favoravel: { min: 25, max: 75 },
      amostra_suficiente: true,
      por_vara: [
        {
          vara: 'Vara Grande', total: 10, suficiente: true, favoravel: 50, desfavoravel: 50,
          intervalo_favoravel: { min: 24, max: 76 }, motivo: null,
        },
        {
          vara: 'Vara Pequena', total: 2, suficiente: false,
          favoravel: null, desfavoravel: null, intervalo_favoravel: null, motivo: 'x',
        },
      ],
    });

    expect(await screen.findByText(/Vara Pequena: 2 processos \(mínimo de 10\)/)).toBeInTheDocument();
    expect(screen.getByText('Sem amostra suficiente para taxa')).toBeInTheDocument();
  });

  it('usa o singular para uma vara com um único processo', async () => {
    renderPage({
      ...base,
      por_vara: [{
        vara: 'Vara X', total: 1, suficiente: false,
        favoravel: null, desfavoravel: null, intervalo_favoravel: null, motivo: 'x',
      }],
    });

    expect(await screen.findByText(/Vara X: 1 processo \(/)).toBeInTheDocument();
  });

  const comparacao = {
    ...base,
    total_analisados: 14,
    taxa_favoravel: 50,
    intervalo_favoravel: { min: 27, max: 73 },
    amostra_suficiente: true,
    por_vara: [
      { vara: 'Vara Grande', total: 12, suficiente: true, favoravel: 50, desfavoravel: 50, intervalo_favoravel: { min: 25, max: 75 }, motivo: null },
      { vara: 'Vara Pequena', total: 2, suficiente: false, favoravel: null, desfavoravel: null, intervalo_favoravel: null, motivo: 'x' },
    ],
    por_ano: [
      { ano: 2024, total: 12, suficiente: true, favoravel: 50, desfavoravel: 50, intervalo_favoravel: { min: 25, max: 75 }, motivo: null },
      { ano: null, total: 2, suficiente: false, favoravel: null, desfavoravel: null, intervalo_favoravel: null, motivo: 'x' },
    ],
  };

  it('compara varas e anos sempre com n e intervalo, sem taxa abaixo do piso', async () => {
    renderPage(comparacao);

    const linha = (await screen.findAllByRole('row')).find((item) => within(item).queryByText('Vara Grande'));
    expect(linha).toHaveTextContent('50% (de 25% a 75%)');
    expect(linha).toHaveTextContent('12');
    const pequena = screen.getAllByRole('row').find((item) => within(item).queryByText('Vara Pequena'));
    expect(pequena).toHaveTextContent('Sem taxa: amostra insuficiente');
    expect(screen.getByText(/Intervalos que se sobrepõem/)).toBeInTheDocument();
  });

  it('abre os processos por trás do número daquela vara', async () => {
    vi.mocked(jurimetriaService.processos).mockResolvedValue({
      total: 1,
      exibidos: 1,
      processos: [{
        id: 1, numero_cnj: '0001234-56', titulo: '', vara: 'Vara Pequena', comarca: 'B', area: 'CIVEL',
        resultado: 'ACORDO', status: 'ARQUIVADO', data_distribuicao: '2024-03-01', cliente_nome: 'Ana',
      }],
    });
    renderPage(comparacao);

    fireEvent.click(await screen.findByRole('button', { name: 'Ver processos: Vara Pequena' }));

    expect(await screen.findByText('0001234-56')).toBeInTheDocument();
    expect(screen.getByText('Acordo')).toBeInTheDocument();
    // sem recuar um dia por causa do fuso
    expect(screen.getByText('01/03/2024')).toBeInTheDocument();
    expect(jurimetriaService.processos).toHaveBeenCalledWith(expect.objectContaining({ vara: 'Vara Pequena' }));
  });

  it('processos sem data são abertos pelo filtro próprio', async () => {
    vi.mocked(jurimetriaService.processos).mockResolvedValue({ total: 0, exibidos: 0, processos: [] });
    renderPage(comparacao);

    fireEvent.click(await screen.findByRole('button', { name: 'Ver processos: Sem data de distribuição' }));

    await waitFor(() => expect(jurimetriaService.processos).toHaveBeenCalledWith(expect.objectContaining({ ano: 'sem_data' })));
  });

  it('mudar o filtro consulta de novo e a exportação leva o mesmo recorte', async () => {
    renderPage(comparacao);

    fireEvent.change(await screen.findByLabelText('Área'), { target: { value: 'CIVEL' } });

    await waitFor(() => expect(jurimetriaService.get).toHaveBeenLastCalledWith({ area: 'CIVEL', ano: '' }));
    fireEvent.click(screen.getByRole('button', { name: /Exportar CSV/ }));
    await waitFor(() => expect(jurimetriaService.exportar).toHaveBeenCalledWith({ area: 'CIVEL', ano: '' }));
  });

  it('erro ao exportar é informado sem derrubar a análise', async () => {
    vi.mocked(jurimetriaService.exportar).mockRejectedValue(new Error('falha'));
    renderPage(comparacao);

    fireEvent.click(await screen.findByRole('button', { name: /Exportar CSV/ }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });
});
