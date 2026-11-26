import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { AxiosError } from 'axios';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Layout from '../components/Layout';
import { AuthContext, type AuthContextValue } from '../contexts/auth';
import { agenteService, processoService } from '../services/juripredict';
import type { AgenteResultado, CasoEstudo, MensagemCaso, Processo } from '../types';
import Agente from './Agente';

vi.mock('../services/juripredict', () => ({
  agenteService: {
    opcoes: vi.fn(), casos: vi.fn(), caso: vi.fn(), criar: vi.fn(), atualizar: vi.fn(), enviar: vi.fn(), excluir: vi.fn(),
  },
  pendenciaService: { get: vi.fn(() => new Promise(() => {})) },
  processoService: { list: vi.fn() },
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

const resultado = (indice: number, perguntas: string[] = []): AgenteResultado => ({
  analise: {
    titulo: 'Limpeza hospitalar', resumo: 'Bom relato, sem prova técnica.',
    criterios: [{ criterio_id: 'pericia', situacao: 'ausente', evidencia: 'Não há laudo.' }],
    melhorias: [], casos_proximos: [], riscos: [],
    resposta: 'Falta a prova técnica; requeira a perícia.', perguntas,
  },
  catalogo: { versao: '0.1', criterios: [{ id: 'pericia', nome: 'Prova técnica', fundamentos: ['CLT, art. 195'] }] },
  medicao: { indice_atual: indice, indice_potencial: 90, ganho: 90 - indice, alertas: [], pontos_fortes: [] },
  casos: [{
    id_sentenca: 's1', numero_cnj: '0016123-45.2024.5.16.0001', tipo_documento: 'Sentença', orgao_julgador: null,
    data_julgamento: null, resultado: 'indeferido', similaridade: 0.9,
  }],
  suposicoes: [], disclaimer: 'Não substitui a avaliação profissional.',
});

let proximoId = 1;
const mensagem = (campos: Partial<MensagemCaso>): MensagemCaso => ({
  id: proximoId++, autor: 'agente', texto: '', status: 'concluida', erro: '', resultado: null, documentos_lidos: [],
  indice_atual: null, indice_potencial: null, criado_em: '2026-11-25T10:00:00Z', ...campos,
});

const caso = (mensagens: MensagemCaso[], campos: Partial<CasoEstudo> = {}): CasoEstudo => ({
  id: 7, titulo: 'Limpeza hospitalar', tema: 'insalubridade', fase: 'instrucao', orgao_julgador: '', provas: ['ppp'], processo: null,
  mensagens, etapa: null, criado_em: '2026-11-25T10:00:00Z', atualizado_em: '2026-11-25T10:00:00Z', ...campos,
});

const pergunta = 'Houve perícia no local de trabalho?';
const conversaPronta = () => caso([
  mensagem({ autor: 'advogado', texto: RELATO }),
  mensagem({ texto: 'Falta a prova técnica; requeira a perícia.', resultado: resultado(58, [pergunta]), indice_atual: 58, indice_potencial: 90 }),
]);

const avancar = () => act(async () => { await vi.advanceTimersByTimeAsync(2000); });

describe('Agente de IA', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(agenteService.opcoes).mockResolvedValue({
      ia_configurada: true, base_configurada: true,
      temas: [{ value: 'insalubridade', label: 'Adicional de insalubridade' }],
      fases: [{ value: 'instrucao', label: 'Em instrução' }, { value: 'recurso', label: 'Em recurso' }],
      provas: [{ value: 'ppp', label: 'PPP' }],
    });
    vi.mocked(agenteService.casos).mockResolvedValue([]);
    vi.mocked(processoService.list).mockResolvedValue([
      { id: 3, numero_cnj: '0016123-45.2024.5.16.0001', titulo: 'Insalubridade hospital' } as Processo,
    ]);
  });

  afterEach(() => { vi.useRealTimers(); });

  it('sem a permissão mostra acesso restrito e não consulta nada', () => {
    render(tela(sessao([])));

    expect(screen.getByRole('alert')).toHaveTextContent('Acesso restrito');
    expect(agenteService.opcoes).not.toHaveBeenCalled();
    expect(agenteService.casos).not.toHaveBeenCalled();
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

  it('cria o caso, acompanha a análise e mostra a resposta com o índice', async () => {
    const pendente = caso([mensagem({ autor: 'advogado', texto: RELATO }), mensagem({ status: 'pendente' })], { titulo: '', etapa: 'retrieve_cases' });
    vi.mocked(agenteService.criar).mockResolvedValue(pendente);
    vi.mocked(agenteService.caso).mockResolvedValue(conversaPronta());
    render(tela());

    fireEvent.change(await screen.findByLabelText('Relato do caso'), { target: { value: RELATO } });
    fireEvent.click(screen.getByLabelText('PPP'));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Analisar caso' })); });

    expect(agenteService.criar).toHaveBeenCalledWith({
      tema: 'insalubridade', fase: 'instrucao', orgao_julgador: '', provas: ['ppp'], processo: null, relato: RELATO,
    });
    expect(await screen.findByText('Buscando decisões parecidas na base do TRT-16...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Aguardando a análise...' })).toBeDisabled();
    await avancar();

    const conversa = within(await screen.findByRole('region', { name: 'Conversa sobre o caso' }));
    expect(conversa.getByText('Falta a prova técnica; requeira a perícia.')).toBeInTheDocument();
    expect(conversa.getByText(/Índice 58 · potencial 90/)).toBeInTheDocument();
    expect(agenteService.casos).toHaveBeenCalledTimes(3);
  });

  it('vincula um processo do escritório e mostra o que a análise leu dos documentos', async () => {
    const lido = caso([
      mensagem({ autor: 'advogado', texto: RELATO, documentos_lidos: [{ nome: 'contrato.pdf', situacao: 'lido' }, { nome: 'foto.doc', situacao: 'sem texto' }] }),
      mensagem({ texto: 'O contrato confirma a função.', resultado: resultado(70), indice_atual: 70, indice_potencial: 90 }),
    ], { processo: 3 });
    vi.mocked(agenteService.criar).mockResolvedValue(lido);
    render(tela());

    fireEvent.change(await screen.findByLabelText('Relato do caso'), { target: { value: RELATO } });
    fireEvent.change(await screen.findByLabelText('Processo do escritório (opcional)'), { target: { value: '3' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Analisar caso' })); });

    expect(agenteService.criar).toHaveBeenCalledWith(expect.objectContaining({ processo: 3 }));
    const conversa = within(await screen.findByRole('region', { name: 'Conversa sobre o caso' }));
    expect(conversa.getByText('Do processo: contrato.pdf (lido), foto.doc (sem texto)')).toBeInTheDocument();
    expect(screen.getByLabelText('Processo do escritório (opcional)')).toHaveValue('3');
  });

  it('a pergunta do agente vira resposta do advogado e a evolução mostra a diferença', async () => {
    vi.mocked(agenteService.casos).mockResolvedValue([{ id: 7, titulo: 'Limpeza hospitalar', tema: 'insalubridade', fase: 'instrucao', indice_atual: 58, atualizado_em: '2026-11-25T10:00:00Z' }]);
    vi.mocked(agenteService.caso).mockResolvedValue(conversaPronta());
    const depois = conversaPronta();
    depois.mensagens.push(
      mensagem({ autor: 'advogado', texto: `${pergunta}\nResposta: sim, favorável.` }),
      mensagem({ texto: 'O laudo atende a prova técnica.', resultado: resultado(83), indice_atual: 83, indice_potencial: 92 }),
    );
    vi.mocked(agenteService.enviar).mockResolvedValue(depois);
    render(tela());

    fireEvent.click(await screen.findByRole('button', { name: /Limpeza hospitalar/ }));
    fireEvent.click(await screen.findByRole('button', { name: pergunta }));
    const campo = screen.getByLabelText('Acrescente um fato, uma prova ou uma resposta');
    expect(campo).toHaveValue(`${pergunta}\nResposta: `);
    fireEvent.change(campo, { target: { value: `${pergunta}\nResposta: sim, favorável.` } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Enviar' })); });

    expect(agenteService.enviar).toHaveBeenCalledWith(7, `${pergunta}\nResposta: sim, favorável.`);
    expect(campo).toHaveValue('');
    expect(screen.getByText(/Índice 83 \(\+25 desde a análise anterior\)/)).toBeInTheDocument();
    const evolucao = within(screen.getByLabelText('Evolução do caso'));
    expect(evolucao.getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Análise 158', 'Análise 283']);
  });

  it('a análise completa mostra os casos parecidos com o resultado de cada um', async () => {
    vi.mocked(agenteService.casos).mockResolvedValue([{ id: 7, titulo: 'Limpeza hospitalar', tema: 'insalubridade', fase: 'instrucao', indice_atual: 58, atualizado_em: '2026-11-25T10:00:00Z' }]);
    vi.mocked(agenteService.caso).mockResolvedValue(conversaPronta());
    render(tela());

    fireEvent.click(await screen.findByRole('button', { name: /Limpeza hospitalar/ }));
    fireEvent.click(await screen.findByText('Ver análise completa'));

    expect(screen.getByText('Indeferido')).toBeInTheDocument();
    expect(screen.getByText('Ausente')).toBeInTheDocument();
  });

  it('erro da análise aparece e libera o envio; erro do servidor não apaga o texto', async () => {
    const comErro = conversaPronta();
    comErro.mensagens.push(mensagem({ autor: 'advogado', texto: 'Mais um fato.' }), mensagem({ status: 'erro', erro: 'A análise se perdeu.' }));
    vi.mocked(agenteService.casos).mockResolvedValue([{ id: 7, titulo: 'Limpeza hospitalar', tema: 'insalubridade', fase: 'instrucao', indice_atual: 58, atualizado_em: '2026-11-25T10:00:00Z' }]);
    vi.mocked(agenteService.caso).mockResolvedValue(comErro);
    vi.mocked(agenteService.enviar).mockRejectedValue(new AxiosError('x', undefined, undefined, undefined, {
      status: 400, data: { texto: ['Aguarde a análise em andamento terminar.'] },
    } as never));
    render(tela());

    fireEvent.click(await screen.findByRole('button', { name: /Limpeza hospitalar/ }));
    expect(await screen.findByText('A análise se perdeu.')).toBeInTheDocument();
    const campo = screen.getByLabelText('Acrescente um fato, uma prova ou uma resposta');
    fireEvent.change(campo, { target: { value: 'De novo.' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Enviar' })); });

    expect(await screen.findByText('Aguarde a análise em andamento terminar.')).toBeInTheDocument();
    expect(campo).toHaveValue('De novo.');
  });

  it('salva os dados do caso e exclui com confirmação', async () => {
    vi.mocked(agenteService.casos).mockResolvedValue([{ id: 7, titulo: 'Limpeza hospitalar', tema: 'insalubridade', fase: 'instrucao', indice_atual: 58, atualizado_em: '2026-11-25T10:00:00Z' }]);
    vi.mocked(agenteService.caso).mockResolvedValue(conversaPronta());
    vi.mocked(agenteService.atualizar).mockResolvedValue(conversaPronta());
    vi.mocked(agenteService.excluir).mockResolvedValue();
    render(tela());

    fireEvent.click(await screen.findByRole('button', { name: /Limpeza hospitalar/ }));
    await screen.findByText('Dados do caso (valem para a próxima mensagem)');
    fireEvent.change(screen.getByLabelText('Fase do processo'), { target: { value: 'recurso' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Salvar dados do caso' })); });
    expect(agenteService.atualizar).toHaveBeenCalledWith(7, { fase: 'recurso', orgao_julgador: '', provas: ['ppp'], processo: null });

    fireEvent.click(screen.getByRole('button', { name: /Excluir caso/ }));
    await act(async () => { fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Excluir' })); });
    expect(agenteService.excluir).toHaveBeenCalledWith(7);
    expect(await screen.findByRole('form', { name: 'Novo caso' })).toBeInTheDocument();
  });

  it('espera o agente hibernado voltar antes de enviar', async () => {
    render(tela());
    fireEvent.change(await screen.findByLabelText('Relato do caso'), { target: { value: RELATO } });
    vi.mocked(agenteService.opcoes).mockRejectedValueOnce(new AxiosError('x', undefined, undefined, undefined, { status: 502, data: {} } as never));
    vi.mocked(agenteService.criar).mockResolvedValue(conversaPronta());
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Analisar caso' })); });

    expect(screen.getByText(/Ligando o agente/)).toBeInTheDocument();
    expect(agenteService.criar).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(5000); });
    await waitFor(() => expect(agenteService.criar).toHaveBeenCalledTimes(1));
  });

  it('trocar de escritório recomeça a tela', async () => {
    const { rerender } = render(tela());
    fireEvent.change(await screen.findByLabelText('Relato do caso'), { target: { value: RELATO } });
    rerender(tela(sessao(['agente.usar'], 'e2')));

    expect(await screen.findByLabelText('Relato do caso')).toHaveValue('');
  });
});
