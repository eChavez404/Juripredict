import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Layout from '../components/Layout';
import { AuthContext, type AuthContextValue } from '../contexts/auth';
import { agenteService } from '../services/juripredict';
import type { AgenteAnalise, AgenteResultado } from '../types';
import Agente from './Agente';

vi.mock('../services/juripredict', () => ({
  agenteService: { opcoes: vi.fn(), iniciar: vi.fn(), consultar: vi.fn() },
  pendenciaService: { get: vi.fn(() => new Promise(() => {})) },
}));

const sessao = (capabilities: string[], escritorio = 'e1') => ({
  user: { id: 1, username: 'u', email: 'u@x.com', nome: 'U' }, memberships: [], capabilities,
  activeEscritorio: { id: escritorio, nome: 'Banca', fuso_horario: 'America/Sao_Paulo' },
  activeMembership: null, loading: false, login: vi.fn(), startSession: vi.fn(), updateUser: vi.fn(),
  selectEscritorio: vi.fn(), hasCapability: (c: string) => capabilities.includes(c), logout: vi.fn(),
} as AuthContextValue);

const tela = (auth = sessao(['agente.usar'])) => (
  <MemoryRouter><AuthContext.Provider value={auth}><Agente /></AuthContext.Provider></MemoryRouter>
);

const RELATO = 'Auxiliar de limpeza em banheiros de hospital, com contato diário com lixo hospitalar.';

const analise = (campos: Partial<AgenteAnalise>): AgenteAnalise => ({
  id: 'assinado:1', status: 'running', step: 'analyze_case', result: null, error: null, ...campos,
});

const resultado: AgenteResultado = {
  analise: {
    titulo: 'Limpeza hospitalar',
    resumo: 'Bom relato, sem prova técnica.',
    criterios: [{ criterio_id: 'pericia', situacao: 'ausente', evidencia: 'Não há laudo.' }],
    melhorias: [{ criterio_id: 'pericia', acao: 'Requerer a perícia', justificativa: 'É a prova central.', caso_ids: ['s1'] }],
    casos_proximos: [{ caso_id: 's1', semelhancas: 'Mesma função.', diferencas: 'Outro hospital.' }],
    riscos: ['Fichas de EPI assinadas'],
  },
  catalogo: { versao: '0.1', criterios: [{ id: 'pericia', nome: 'Prova técnica', fundamentos: ['CLT, art. 195'] }] },
  medicao: { indice_atual: 40, indice_potencial: 70, ganho: 30, alertas: ['Falta laudo'], pontos_fortes: [] },
  casos: [{
    id_sentenca: 's1', numero_cnj: '0016123-45.2024.5.16.0001', tipo_documento: 'Sentença', orgao_julgador: null,
    data_julgamento: null, resultado: null, similaridade: 0.912,
  }],
  suposicoes: [],
  disclaimer: 'Não substitui a avaliação profissional.',
};

const enviar = async () => {
  fireEvent.change(await screen.findByLabelText('Relato do caso'), { target: { value: RELATO } });
  fireEvent.click(screen.getByLabelText('PPP'));
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Analisar caso' })); });
};

const semResposta = (status = 502) => new AxiosError('x', undefined, undefined, undefined, {
  status, data: { detail: `falha ${status}` },
} as never);

const avancar = () => act(async () => { await vi.advanceTimersByTimeAsync(2000); });

describe('Agente', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(agenteService.opcoes).mockResolvedValue({
      temas: [{ value: 'insalubridade', label: 'Adicional de insalubridade' }],
      fases: [{ value: 'instrucao', label: 'Em instrução' }],
      provas: [{ value: 'ppp', label: 'PPP' }],
    });
    vi.mocked(agenteService.iniciar).mockResolvedValue(analise({}));
  });

  afterEach(() => { vi.useRealTimers(); });

  it('sem a permissão mostra acesso restrito e não consulta o agente', () => {
    render(tela(sessao([])));

    expect(screen.getByRole('alert')).toHaveTextContent('Acesso restrito');
    expect(agenteService.opcoes).not.toHaveBeenCalled();
  });

  it('o item do menu só aparece para quem pode usar', () => {
    for (const [capabilities, visivel] of [[['agente.usar'], true], [[], false]] as const) {
      const { unmount } = render(
        <MemoryRouter><AuthContext.Provider value={sessao([...capabilities])}><Layout /></AuthContext.Provider></MemoryRouter>,
      );
      expect(screen.queryByRole('button', { name: 'Agente de IA' }) !== null).toBe(visivel);
      unmount();
    }
  });

  it('envia o caso, acompanha e mostra o resultado com a ressalva', async () => {
    vi.mocked(agenteService.consultar)
      .mockResolvedValueOnce(analise({ step: 'measure_case' }))
      .mockResolvedValueOnce(analise({ status: 'done', result: resultado }));
    render(tela());
    await enviar();

    expect(agenteService.iniciar).toHaveBeenCalledWith({
      tema: 'insalubridade', fase: 'instrucao', relato: RELATO, provas: ['ppp'], orgao_julgador: '', duvida: '',
    });
    expect(screen.getByRole('button', { name: 'Analisando...' })).toBeDisabled();
    await avancar();
    expect(screen.getByText('Calculando os índices...')).toBeInTheDocument();
    await avancar();

    const bloco = within(screen.getByRole('region', { name: 'Resultado da análise' }));
    for (const texto of ['40', '70', '+30', 'Ausente', 'Requerer a perícia', 'Fichas de EPI assinadas', 'Falta laudo']) {
      expect(bloco.getByText(texto)).toBeInTheDocument();
    }
    expect(bloco.getByText(/Não é probabilidade de êxito/)).toBeInTheDocument();
    expect(bloco.getByText('Apoio: 0016123-45.2024.5.16.0001')).toBeInTheDocument();
    expect(agenteService.consultar).toHaveBeenCalledTimes(2);
    expect(agenteService.consultar).toHaveBeenCalledWith('assinado:1');
  });

  it('mostra o erro do agente e deixa tentar de novo, sem perder o relato', async () => {
    vi.mocked(agenteService.consultar).mockResolvedValue(
      analise({ status: 'error', error: 'A chave do provedor de IA não está configurada no serviço.' }),
    );
    render(tela());
    await enviar();
    await avancar();

    expect(screen.getByRole('alert')).toHaveTextContent('A chave do provedor de IA');
    expect(screen.getByRole('button', { name: 'Analisar caso' })).toBeEnabled();
    expect(screen.getByLabelText('Relato do caso')).toHaveValue(RELATO);
  });

  it('com o agente desligado avisa e não mostra o formulário', async () => {
    vi.mocked(agenteService.opcoes).mockRejectedValue(new Error('503'));
    render(tela());

    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByLabelText('Relato do caso')).not.toBeInTheDocument();
  });

  it('espera o agente hibernado voltar e então mostra o formulário', async () => {
    vi.mocked(agenteService.opcoes).mockRejectedValueOnce(semResposta());
    render(tela());

    expect(await screen.findByText(/Ligando o agente/)).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });

    expect(await screen.findByLabelText('Relato do caso')).toBeInTheDocument();
    expect(screen.queryByText(/Ligando o agente/)).not.toBeInTheDocument();
  });

  it('desiste depois de dois minutos e, sem configuração, nem espera', async () => {
    vi.mocked(agenteService.opcoes).mockRejectedValue(semResposta());
    const { unmount } = render(tela());
    await act(async () => { await vi.advanceTimersByTimeAsync(130_000); });
    expect(screen.getByRole('alert')).toHaveTextContent('falha 502');
    unmount();

    vi.mocked(agenteService.opcoes).mockClear().mockRejectedValue(semResposta(503));
    render(tela());
    expect(await screen.findByRole('alert')).toHaveTextContent('falha 503');
    expect(agenteService.opcoes).toHaveBeenCalledTimes(1);
  });

  it('acorda o agente antes de enviar e nunca repete o envio', async () => {
    render(tela());
    await screen.findByLabelText('Relato do caso');
    vi.mocked(agenteService.opcoes).mockRejectedValueOnce(semResposta());
    vi.mocked(agenteService.iniciar).mockRejectedValue(semResposta());
    await enviar();

    expect(screen.getByText(/Ligando o agente/)).toBeInTheDocument();
    expect(agenteService.iniciar).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });

    expect(agenteService.iniciar).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('alert')).toHaveTextContent('falha 502');
  });

  it('uma consulta sem resposta não derruba a análise em andamento', async () => {
    vi.mocked(agenteService.consultar)
      .mockRejectedValueOnce(semResposta())
      .mockResolvedValueOnce(analise({ status: 'done', result: resultado }));
    render(tela());
    await enviar();
    await act(async () => { await vi.advanceTimersByTimeAsync(8000); });

    expect(screen.getByRole('region', { name: 'Resultado da análise' })).toBeInTheDocument();
  });

  it('para de consultar ao sair da tela', async () => {
    const { unmount } = render(tela());
    await enviar();
    unmount();
    await avancar();

    expect(agenteService.consultar).not.toHaveBeenCalled();
  });

  it('trocar de escritório limpa o caso', async () => {
    const { rerender } = render(tela());
    fireEvent.change(await screen.findByLabelText('Relato do caso'), { target: { value: RELATO } });
    rerender(tela(sessao(['agente.usar'], 'e2')));

    expect(await screen.findByLabelText('Relato do caso')).toHaveValue('');
  });
});
