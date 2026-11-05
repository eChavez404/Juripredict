import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { eventoService, prazoService } from '../../services/juripredict';
import type { PrazoCalculado, Processo } from '../../types';
import CalculadoraPrazoModal from './CalculadoraPrazoModal';

vi.mock('../../services/juripredict', () => ({
  eventoService: { create: vi.fn() },
  prazoService: { calcular: vi.fn() },
}));

const calculado = (extra: Partial<PrazoCalculado> = {}): PrazoCalculado => ({
  data_base: '2026-03-30',
  dias: 5,
  tipo: 'INTIMACAO',
  area: 'TRABALHISTA',
  fundamento: 'CLT, arts. 775 e 775-A',
  marco_inicial: '2026-03-30',
  primeiro_dia_contado: '2026-03-31',
  vencimento: '2026-04-06',
  fins_de_semana_nao_contados: 2,
  dias_nao_contados: [],
  dias_a_conferir: [{ data: '2026-04-03', motivo: 'Sexta-feira da Paixão' }],
  ressalvas: ['Cálculo de apoio: confira o calendário do tribunal.'],
  ...extra,
});

const processo = { id: 7, numero_cnj: '0001', area: 'TRABALHISTA', cliente_nome: 'Ana' } as Processo;

const abrir = (props: Partial<Parameters<typeof CalculadoraPrazoModal>[0]> = {}) => {
  const onClose = vi.fn();
  const onCriado = vi.fn();
  render(<CalculadoraPrazoModal open dataBase="2026-03-30" onClose={onClose} onCriado={onCriado} {...props} />);
  return { onClose, onCriado };
};

const calcular = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Calcular' }));
  await screen.findByText('Vencimento');
};

describe('CalculadoraPrazoModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(prazoService.calcular).mockResolvedValue(calculado());
  });

  it('mostra o vencimento por extenso sem recuar um dia por causa do fuso', async () => {
    abrir();
    await calcular();

    expect(screen.getByText(/06 de abril de 2026/)).toBeInTheDocument();
    expect(screen.getByText(/CLT, arts. 775 e 775-A/)).toBeInTheDocument();
  });

  it('marcar um dia a conferir refaz a conta informando a suspensão', async () => {
    abrir();
    await calcular();
    vi.mocked(prazoService.calcular).mockResolvedValue(calculado({ vencimento: '2026-04-07', dias_a_conferir: [] }));

    fireEvent.click(screen.getByRole('checkbox', { name: /Sexta-feira da Paixão/ }));

    await screen.findByText(/07 de abril de 2026/);
    expect(prazoService.calcular).toHaveBeenLastCalledWith(expect.objectContaining({ suspensoes: ['2026-04-03'] }));
    // continua visível e marcado, para poder desfazer
    expect(screen.getByRole('checkbox', { name: /Sexta-feira da Paixão/ })).toBeChecked();
  });

  it('mudar um campo apaga o resultado: não se grava a data de outro cálculo', async () => {
    abrir();
    await calcular();

    fireEvent.change(screen.getByLabelText('Prazo em dias úteis'), { target: { value: '15' } });

    expect(screen.queryByText('Vencimento')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Adicionar à agenda/ })).not.toBeInTheDocument();
  });

  it('adiciona à agenda com o processo e a memória do cálculo', async () => {
    const { onClose, onCriado } = abrir({ processo, titulo: 'Prazo: Juntada' });
    await calcular();

    fireEvent.click(screen.getByRole('button', { name: /Adicionar à agenda/ }));

    await waitFor(() => expect(onCriado).toHaveBeenCalled());
    const enviado = vi.mocked(eventoService.create).mock.calls[0][0];
    expect(enviado).toMatchObject({ titulo: 'Prazo: Juntada', tipo: 'PRAZO', processo: 7 });
    expect(new Date(enviado.inicio as string).toLocaleDateString('pt-BR')).toBe('06/04/2026');
    expect(enviado.descricao).toContain('Vencimento: 06/04/2026');
    expect(enviado.descricao).toContain('confira o calendário do tribunal');
    expect(onClose).toHaveBeenCalled();
  });

  it('exige título antes de adicionar', async () => {
    abrir();
    await calcular();

    expect(screen.getByRole('button', { name: /Adicionar à agenda/ })).toBeDisabled();
  });

  it('não calcula processo de área com contagem própria', () => {
    abrir({ processo: { ...processo, area: 'CRIMINAL' } });

    expect(screen.getByText(/área com contagem própria/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Calcular' })).toBeDisabled();
  });

  it('usa a área do processo escolhido, e não a do seletor', async () => {
    abrir({ processos: [{ ...processo, area: 'CIVEL' }] });
    fireEvent.change(screen.getByLabelText('Processo relacionado'), { target: { value: '7' } });
    await calcular();

    expect(prazoService.calcular).toHaveBeenCalledWith(expect.objectContaining({ area: 'CIVEL' }));
    expect(screen.getByLabelText('Área')).toBeDisabled();
  });

  it('informa erro da API sem mostrar resultado', async () => {
    vi.mocked(prazoService.calcular).mockRejectedValue(new Error('falha'));
    abrir();

    fireEvent.click(screen.getByRole('button', { name: 'Calcular' }));

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('Vencimento')).not.toBeInTheDocument();
  });

  it('resposta atrasada de um cálculo antigo não sobrescreve a mudança feita depois', async () => {
    let resolver: (valor: PrazoCalculado) => void = () => undefined;
    vi.mocked(prazoService.calcular).mockReturnValue(new Promise((resolve) => { resolver = resolve; }));
    abrir();

    fireEvent.click(screen.getByRole('button', { name: 'Calcular' }));
    fireEvent.change(screen.getByLabelText('Prazo em dias úteis'), { target: { value: '15' } });
    resolver(calculado());

    await waitFor(() => expect(prazoService.calcular).toHaveBeenCalled());
    await Promise.resolve();
    expect(screen.queryByText('Vencimento')).not.toBeInTheDocument();
  });
});
