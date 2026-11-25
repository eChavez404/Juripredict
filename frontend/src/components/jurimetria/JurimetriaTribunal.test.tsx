import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { jurimetriaService } from '../../services/juripredict';
import type { JurimetriaTribunalDisponivel, TaxaTribunal } from '../../types';
import JurimetriaTribunal from './JurimetriaTribunal';

vi.mock('../../services/juripredict', () => ({
  jurimetriaService: { tribunal: vi.fn(), decisoesTribunal: vi.fn() },
}));

const SUPRIMIDA = 'O resultado de cada decisão foi lido por regra automática e ainda não foi conferido por leitura humana.';

const taxa = (campos: Partial<TaxaTribunal> = {}): TaxaTribunal => ({
  total: 120, suficiente: true, favoravel: null, desfavoravel: null, intervalo_favoravel: null,
  motivo: SUPRIMIDA, cobertura: null, ...campos,
});

const base: JurimetriaTribunalDisponivel = {
  disponivel: true,
  filtros: { tema: 'insalubridade' },
  geral: taxa(),
  fora_da_taxa: [{ motivo: 'Ação coletiva (sindicato ou Ministério Público)', total: 7 }],
  por_vara: [{ vara: 'Vara do Trabalho de Balsas', ...taxa({ total: 118 }) }],
  por_ano: [{ ano: 2025, ...taxa({ total: 90 }) }],
  validacao: { rotulo_conferido: false, motivo: SUPRIMIDA, gold_set: null, cobertura_medida: false },
  opcoes: {
    temas: [{ valor: 'insalubridade', rotulo: 'Adicional de insalubridade' }, { valor: 'periculosidade', rotulo: 'Adicional de periculosidade' }],
    varas: ['Vara do Trabalho de Balsas'],
    anos: [2026, 2025],
  },
  fonte: { origem: 'Falcão (CSJT)', inicio: '2024-01-05', fim: '2026-11-14', versao: '2.0/regra', importado_em: '2026-11-25T10:00:00Z' },
  populacao: 'Pedidos julgados no mérito em sentença de 1º grau do TRT-16.',
  criterio: 'Mesmo pedido e, quando escolhidos, mesma vara e mesmo ano.',
  piso_amostra: 10,
};

describe('JurimetriaTribunal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sem conferência humana mostra o n e o motivo, nunca um percentual', async () => {
    vi.mocked(jurimetriaService.tribunal).mockResolvedValue(base);
    render(<JurimetriaTribunal />);

    expect(await screen.findByText('Taxas ainda suprimidas.')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Ver as 120 sentenças/ })).toBeInTheDocument();
    expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument();
    expect(screen.getByText(/Cobertura da fonte neste recorte: não medida/)).toBeInTheDocument();
    expect(screen.getByText('Ação coletiva (sindicato ou Ministério Público)')).toBeInTheDocument();
  });

  it('com a taxa liberada mostra percentual, intervalo e cobertura', async () => {
    const liberada = taxa({ favoravel: 64, desfavoravel: 36, intervalo_favoravel: { min: 55, max: 72 }, motivo: null, cobertura: 81 });
    vi.mocked(jurimetriaService.tribunal).mockResolvedValue({
      ...base, geral: liberada, validacao: { ...base.validacao, rotulo_conferido: true, motivo: null },
    });
    render(<JurimetriaTribunal />);

    expect(await screen.findByText('64%')).toBeInTheDocument();
    expect(screen.getByText('IC 95%: 55% a 72%')).toBeInTheDocument();
    expect(screen.getByText('Cobertura da fonte neste recorte: 81%')).toBeInTheDocument();
    expect(screen.queryByText('Taxas ainda suprimidas.')).not.toBeInTheDocument();
  });

  it('trocar o pedido consulta de novo e limpa vara e ano', async () => {
    vi.mocked(jurimetriaService.tribunal).mockResolvedValue(base);
    render(<JurimetriaTribunal />);

    fireEvent.change(await screen.findByLabelText('Vara'), { target: { value: 'Vara do Trabalho de Balsas' } });
    await waitFor(() => expect(jurimetriaService.tribunal).toHaveBeenLastCalledWith({ tema: 'insalubridade', vara: 'Vara do Trabalho de Balsas', ano: '' }));
    fireEvent.change(screen.getByLabelText('Pedido'), { target: { value: 'periculosidade' } });

    await waitFor(() => expect(jurimetriaService.tribunal).toHaveBeenLastCalledWith({ tema: 'periculosidade', vara: '', ano: '' }));
  });

  it('abre as sentenças da vara, filtra por resultado e mostra o trecho', async () => {
    vi.mocked(jurimetriaService.tribunal).mockResolvedValue(base);
    vi.mocked(jurimetriaService.decisoesTribunal).mockResolvedValue({
      total: 1, exibidos: 1, contagem: { deferido: 70, indeferido: 48 },
      decisoes: [{
        numero_cnj: '0016123-45.2025.5.16.0011', vara: 'Vara do Trabalho de Balsas', data_sentenca: '2025-03-01',
        resultado: 'deferido', grau: 40, mecanismo: 'regra_direta', trecho: 'condenar a [parte] ao adicional em grau máximo',
      }],
    });
    render(<JurimetriaTribunal />);

    fireEvent.click(await screen.findByRole('button', { name: 'Ver sentenças: Vara do Trabalho de Balsas' }));
    const modal = within(await screen.findByRole('dialog'));
    expect(await modal.findByText('0016123-45.2025.5.16.0011')).toBeInTheDocument();
    expect(modal.getByText('Máximo (40%)')).toBeInTheDocument();
    expect(modal.getByText('Lido no dispositivo')).toBeInTheDocument();
    fireEvent.click(modal.getByRole('button', { name: 'Ver trecho' }));
    expect(modal.getByText('condenar a [parte] ao adicional em grau máximo')).toBeInTheDocument();
    expect(modal.getByText('Trecho do dispositivo · 0016123-45.2025.5.16.0011')).toBeInTheDocument();

    fireEvent.click(modal.getByRole('button', { name: 'Indeferidas (48)' }));
    await waitFor(() => expect(jurimetriaService.decisoesTribunal).toHaveBeenLastCalledWith({
      tema: 'insalubridade', vara: 'Vara do Trabalho de Balsas', ano: '', resultado: 'indeferido',
    }));
  });

  it('sem base importada avisa em vez de mostrar zero', async () => {
    vi.mocked(jurimetriaService.tribunal).mockResolvedValue({ disponivel: false });
    render(<JurimetriaTribunal />);

    expect(await screen.findByText(/ainda não foi importada/)).toBeInTheDocument();
  });
});
