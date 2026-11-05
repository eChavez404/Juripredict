import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { conviteService } from '../../features/escritorios/api';
import type { Convite } from '../../features/escritorios/types';
import ConvitesPanel from './ConvitesPanel';

vi.mock('../../features/escritorios/api', () => ({
  conviteService: { list: vi.fn(), create: vi.fn(), revoke: vi.fn() },
}));

const convite: Convite = {
  id: 'c1',
  email: 'pendente@x.com',
  papel: 'ADVOGADO',
  criado_em: '2026-10-01T10:00:00Z',
  expira_em: '2026-10-08T10:00:00Z',
};

describe('ConvitesPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lista os convites pendentes com o papel traduzido', async () => {
    vi.mocked(conviteService.list).mockResolvedValue([convite]);
    render(<ConvitesPanel escritorioId="office-1" />);

    expect(await screen.findByText('pendente@x.com')).toBeInTheDocument();
    expect(screen.getByText('Advogado')).toBeInTheDocument();
    expect(conviteService.list).toHaveBeenCalledWith('office-1');
  });

  it('mostra o estado vazio quando não há convites', async () => {
    vi.mocked(conviteService.list).mockResolvedValue([]);
    render(<ConvitesPanel escritorioId="office-1" />);

    expect(await screen.findByText('Nenhum convite pendente.')).toBeInTheDocument();
  });

  it('envia o convite com o papel escolhido e recarrega a lista', async () => {
    vi.mocked(conviteService.list).mockResolvedValue([]);
    vi.mocked(conviteService.create).mockResolvedValue(convite);
    render(<ConvitesPanel escritorioId="office-1" />);
    await screen.findByText('Nenhum convite pendente.');

    fireEvent.click(screen.getByRole('button', { name: /Convidar pessoa/ }));
    fireEvent.change(screen.getByLabelText('E-mail'), { target: { value: 'novo@x.com' } });
    fireEvent.change(screen.getByLabelText('Papel'), { target: { value: 'ESTAGIARIO' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enviar convite' }));

    await waitFor(() => expect(conviteService.create).toHaveBeenCalledWith(
      'office-1',
      { email: 'novo@x.com', papel: 'ESTAGIARIO' },
    ));
    expect(await screen.findByText('Convite enviado para novo@x.com.')).toBeInTheDocument();
    expect(conviteService.list).toHaveBeenCalledTimes(2);
  });

  it('não oferece proprietário como papel de convite', async () => {
    vi.mocked(conviteService.list).mockResolvedValue([]);
    render(<ConvitesPanel escritorioId="office-1" />);
    await screen.findByText('Nenhum convite pendente.');

    fireEvent.click(screen.getByRole('button', { name: /Convidar pessoa/ }));

    const opcoes = screen.getAllByRole('option').map((item) => item.textContent);
    expect(opcoes).toEqual(['Administrador', 'Advogado', 'Estagiário']);
  });

  it('revoga só depois da confirmação', async () => {
    vi.mocked(conviteService.list).mockResolvedValue([convite]);
    vi.mocked(conviteService.revoke).mockResolvedValue(undefined);
    render(<ConvitesPanel escritorioId="office-1" />);
    await screen.findByText('pendente@x.com');

    fireEvent.click(screen.getByRole('button', { name: 'Revogar' }));
    expect(conviteService.revoke).not.toHaveBeenCalled();

    const confirmar = screen.getAllByRole('button', { name: 'Revogar' }).at(-1)!;
    fireEvent.click(confirmar);

    await waitFor(() => expect(conviteService.revoke).toHaveBeenCalledWith('office-1', 'c1'));
  });
});
