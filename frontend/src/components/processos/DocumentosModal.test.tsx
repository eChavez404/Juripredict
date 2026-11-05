import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { processoService } from '../../services/juripredict';
import type { DocumentoProcesso, Processo } from '../../types';
import DocumentosModal from './DocumentosModal';

vi.mock('../../services/juripredict', () => ({
  processoService: { documentos: vi.fn(), anexarDocumento: vi.fn(), removerDocumento: vi.fn() },
}));

const processo = { id: 7, numero_cnj: '0001234-56.2023.5.16.0001' } as Processo;

const doc = (id: number, nome: string, extra: Partial<DocumentoProcesso> = {}): DocumentoProcesso => ({
  id, nome, tamanho: 2048, url: `http://x/${nome}`, enviado_por_nome: 'Ana', criado_em: '2024-03-01T12:00:00Z', ...extra,
});

const abrir = async (lista: DocumentoProcesso[]) => {
  vi.mocked(processoService.documentos).mockResolvedValue(lista);
  render(<DocumentosModal processo={processo} onClose={vi.fn()} />);
  await waitFor(() => expect(processoService.documentos).toHaveBeenCalledWith(7));
};

describe('DocumentosModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('não consulta nada sem processo selecionado', () => {
    render(<DocumentosModal processo={null} onClose={vi.fn()} />);

    expect(processoService.documentos).not.toHaveBeenCalled();
  });

  it('lista nome, tamanho, data e quem enviou, com link para abrir', async () => {
    await abrir([doc(1, 'prova.pdf'), doc(2, 'sentenca.pdf', { tamanho: 3 * 1024 * 1024, enviado_por_nome: null })]);

    expect(await screen.findByRole('link', { name: 'prova.pdf' })).toHaveAttribute('href', 'http://x/prova.pdf');
    expect(screen.getByText(/2 KB · .* · Ana/)).toBeInTheDocument();
    expect(screen.getByText(/3,0 MB/)).toBeInTheDocument();
    expect(screen.getByText('2 documentos')).toBeInTheDocument();
  });

  it('avisa quando o processo ainda não tem documentos', async () => {
    await abrir([]);

    expect(await screen.findByText('Nenhum documento anexado a este processo.')).toBeInTheDocument();
  });

  it('anexa o arquivo escolhido e o coloca no topo da lista', async () => {
    await abrir([doc(1, 'antigo.pdf')]);
    vi.mocked(processoService.anexarDocumento).mockResolvedValue(doc(2, 'novo.pdf'));
    await screen.findByText('antigo.pdf');

    const arquivo = new File(['%PDF'], 'novo.pdf', { type: 'application/pdf' });
    fireEvent.change(screen.getByLabelText('Selecionar documento'), { target: { files: [arquivo] } });

    expect(await screen.findByText('novo.pdf')).toBeInTheDocument();
    expect(processoService.anexarDocumento).toHaveBeenCalledWith(7, arquivo);
    const nomes = screen.getAllByRole('link').map((link) => link.textContent);
    expect(nomes).toEqual(['novo.pdf', 'antigo.pdf']);
  });

  it('mostra o motivo quando o servidor recusa o arquivo e mantém a lista', async () => {
    await abrir([doc(1, 'antigo.pdf')]);
    vi.mocked(processoService.anexarDocumento).mockRejectedValue(new Error('x'));
    await screen.findByText('antigo.pdf');

    fireEvent.change(screen.getByLabelText('Selecionar documento'), {
      target: { files: [new File(['x'], 'ruim.pdf')] },
    });

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('antigo.pdf')).toBeInTheDocument();
  });

  it('só exclui depois da confirmação', async () => {
    await abrir([doc(1, 'a.pdf'), doc(2, 'b.pdf')]);
    vi.mocked(processoService.removerDocumento).mockResolvedValue(undefined);
    await screen.findByText('a.pdf');

    fireEvent.click(screen.getByRole('button', { name: 'Excluir documento a.pdf' }));
    expect(processoService.removerDocumento).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Excluir' }));

    await waitFor(() => expect(screen.queryByText('a.pdf')).not.toBeInTheDocument());
    expect(processoService.removerDocumento).toHaveBeenCalledWith(7, 1);
    expect(screen.getByText('b.pdf')).toBeInTheDocument();
  });

  it('cancelar a confirmação não exclui nada', async () => {
    await abrir([doc(1, 'a.pdf')]);
    await screen.findByText('a.pdf');

    fireEvent.click(screen.getByRole('button', { name: 'Excluir documento a.pdf' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(processoService.removerDocumento).not.toHaveBeenCalled();
    expect(screen.getByText('a.pdf')).toBeInTheDocument();
  });
});
