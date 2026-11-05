import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextValue } from '../../contexts/auth';
import { pendenciaService } from '../../services/juripredict';
import type { EventoAgenda, Pendencias } from '../../types';
import CentralPendencias from './CentralPendencias';

vi.mock('../../services/juripredict', () => ({ pendenciaService: { get: vi.fn() } }));

const evento = (id: number, titulo: string, inicio: string) => ({
  id, titulo, inicio, tipo: 'PRAZO', processo_numero: '0001',
} as EventoAgenda);

const vazio: Pendencias = {
  urgentes: 0, total_vencidos: 0, total_proximos: 0, vencidos: [], proximos: [], andamentos_recentes: [],
};

const sessao = (ativo: boolean) => ({
  activeEscritorio: ativo ? { id: 'e1', nome: 'E', fuso_horario: 'America/Sao_Paulo' } : null,
} as unknown as AuthContextValue);

const Local = () => <output data-testid="local">{useLocation().pathname + useLocation().search}</output>;

const renderizar = (ativo = true) => render(
  <MemoryRouter>
    <AuthContext.Provider value={sessao(ativo)}><CentralPendencias /><Local /></AuthContext.Provider>
  </MemoryRouter>,
);

describe('CentralPendencias', () => {
  beforeEach(() => vi.clearAllMocks());

  it('mostra o número de urgentes no sino, em palavras para leitor de tela', async () => {
    vi.mocked(pendenciaService.get).mockResolvedValue({ ...vazio, urgentes: 3 });
    renderizar();

    expect(await screen.findByRole('button', { name: 'Pendências: 3 urgentes' })).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('sem urgentes, o sino não mostra contador', async () => {
    vi.mocked(pendenciaService.get).mockResolvedValue(vazio);
    renderizar();

    await waitFor(() => expect(pendenciaService.get).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: 'Pendências' })).toBeInTheDocument();
  });

  it('não consulta nada sem escritório ativo', () => {
    renderizar(false);

    expect(pendenciaService.get).not.toHaveBeenCalled();
  });

  it('lista vencidos e abre a agenda na semana do compromisso', async () => {
    vi.mocked(pendenciaService.get).mockResolvedValue({
      ...vazio,
      urgentes: 1,
      total_vencidos: 1,
      vencidos: [evento(1, 'Recurso ordinário', '2026-03-10T12:00:00Z')],
    });
    renderizar();

    fireEvent.click(await screen.findByRole('button', { name: /Pendências: 1 urgente/ }));
    fireEvent.click(await screen.findByRole('button', { name: /Recurso ordinário/ }));

    expect(screen.getByTestId('local')).toHaveTextContent('/agenda?data=2026-03-10');
    expect(screen.queryByText('Prazos vencidos (1)')).not.toBeInTheDocument();
  });

  it('diz quando não há nada pendente', async () => {
    vi.mocked(pendenciaService.get).mockResolvedValue(vazio);
    renderizar();

    fireEvent.click(screen.getByRole('button', { name: 'Pendências' }));

    expect(await screen.findByText('Nada pendente nos próximos 7 dias.')).toBeInTheDocument();
  });

  it('falha na consulta não quebra o app e é informada ao abrir', async () => {
    vi.mocked(pendenciaService.get).mockRejectedValue(new Error('fora do ar'));
    renderizar();

    fireEvent.click(screen.getByRole('button', { name: 'Pendências' }));

    expect(await screen.findByText('Não foi possível carregar agora.')).toBeInTheDocument();
  });

  it('fecha com Esc', async () => {
    vi.mocked(pendenciaService.get).mockResolvedValue(vazio);
    renderizar();
    fireEvent.click(screen.getByRole('button', { name: 'Pendências' }));
    await screen.findByText('Abrir agenda');

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(screen.queryByText('Abrir agenda')).not.toBeInTheDocument();
  });
});
