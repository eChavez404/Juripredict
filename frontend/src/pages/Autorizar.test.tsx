import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AxiosError, type AxiosResponse } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { contaService } from '../features/conta/api';
import Autorizar from './Autorizar';

vi.mock('../features/conta/api', () => ({
  contaService: { pedidoOAuth: vi.fn(), decidirOAuth: vi.fn() },
}));

const ROTA = '/autorizar?client_id=abc&redirect_uri=https%3A%2F%2Fapp.invalid%2Fcb&state=s1&parametro_estranho=x';
const irPara = vi.fn();

const erroDaApi = (data: unknown) => new AxiosError('x', '400', undefined, undefined, {
  status: 400, data,
} as AxiosResponse);

const abrir = () => render(
  <MemoryRouter initialEntries={[ROTA]}>
    <Autorizar irPara={irPara} />
  </MemoryRouter>,
);

describe('Autorizar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(contaService.pedidoOAuth).mockResolvedValue({
      aplicativo: 'Claude', destino: 'app.invalid', escopo: 'leitura', escritorios: [{ id: 'e1', nome: 'Banca da Ana' }],
    });
  });

  it('mostra quem pede, o que pode ler, e só repassa os parâmetros do OAuth', async () => {
    abrir();

    expect(await screen.findByRole('heading', { name: 'Claude quer acessar o JuriPredict' })).toBeInTheDocument();
    expect(screen.getByText(/Nunca cria, altera ou apaga nada/)).toBeInTheDocument();
    expect(screen.getByText('Banca da Ana')).toBeInTheDocument();
    expect(screen.getByText('app.invalid')).toBeInTheDocument();
    expect(contaService.pedidoOAuth).toHaveBeenCalledWith({
      client_id: 'abc', redirect_uri: 'https://app.invalid/cb', state: 's1',
    });
  });

  it('permitir grava a decisão com o escritório e volta ao aplicativo', async () => {
    vi.mocked(contaService.decidirOAuth).mockResolvedValue({ redirecionar: 'https://app.invalid/cb?code=c1&state=s1' });
    abrir();

    fireEvent.click(await screen.findByRole('button', { name: 'Permitir acesso' }));

    await waitFor(() => expect(irPara).toHaveBeenCalledWith('https://app.invalid/cb?code=c1&state=s1'));
    expect(contaService.decidirOAuth).toHaveBeenCalledWith(expect.objectContaining({
      client_id: 'abc', permitir: true, escritorio_id: 'e1',
    }));
  });

  it('com mais de um escritório a pessoa escolhe qual', async () => {
    vi.mocked(contaService.pedidoOAuth).mockResolvedValue({
      aplicativo: 'Claude', destino: 'app.invalid', escopo: 'leitura',
      escritorios: [{ id: 'e1', nome: 'Banca da Ana' }, { id: 'e2', nome: 'Outra banca' }],
    });
    vi.mocked(contaService.decidirOAuth).mockResolvedValue({ redirecionar: 'https://app.invalid/cb' });
    abrir();

    fireEvent.change(await screen.findByLabelText('Escritório'), { target: { value: 'e2' } });
    fireEvent.click(screen.getByRole('button', { name: 'Permitir acesso' }));

    await waitFor(() => expect(contaService.decidirOAuth).toHaveBeenCalledWith(
      expect.objectContaining({ escritorio_id: 'e2' }),
    ));
  });

  it('negar também volta ao aplicativo', async () => {
    vi.mocked(contaService.decidirOAuth).mockResolvedValue({ redirecionar: 'https://app.invalid/cb?error=access_denied' });
    abrir();

    fireEvent.click(await screen.findByRole('button', { name: 'Negar' }));

    await waitFor(() => expect(irPara).toHaveBeenCalledWith('https://app.invalid/cb?error=access_denied'));
    expect(contaService.decidirOAuth).toHaveBeenCalledWith(expect.objectContaining({ permitir: false }));
  });

  it('pedido sem retorno seguro mostra o motivo e não redireciona', async () => {
    vi.mocked(contaService.pedidoOAuth).mockRejectedValue(erroDaApi({ detail: 'Aplicativo desconhecido.' }));
    abrir();

    expect(await screen.findByRole('alert')).toHaveTextContent('Aplicativo desconhecido.');
    expect(irPara).not.toHaveBeenCalled();
  });

  it('erro que deve voltar ao aplicativo é devolvido pela URL indicada', async () => {
    vi.mocked(contaService.pedidoOAuth).mockRejectedValue(
      erroDaApi({ detail: 'PKCE obrigatório.', redirecionar: 'https://app.invalid/cb?error=invalid_request' }),
    );
    abrir();

    await waitFor(() => expect(irPara).toHaveBeenCalledWith('https://app.invalid/cb?error=invalid_request'));
  });
});
