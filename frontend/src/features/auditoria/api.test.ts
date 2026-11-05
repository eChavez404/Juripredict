import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../../services/api';
import { auditoriaService } from './api';

vi.mock('../../services/api', () => ({ default: { get: vi.fn() } }));

const evento = (acao: string, alteracoes: Record<string, unknown>) => ({
  id: 'e1', acao, alteracoes, ator: { email: 'ana@x.com' }, recurso_tipo: 'processo', recurso_id: '7',
  criado_em: '2026-10-20T10:00:00Z',
});

describe('auditoriaService', () => {
  beforeEach(() => vi.clearAllMocks());

  it('descreve a leitura por agente com credencial, caminho e status', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [evento('token_api.leitura', {
      credencial: 'jp_abc1234', caminho: 'processos/7/andamentos/', status: 200, filtros: [],
    })] });

    const [item] = await auditoriaService.list();

    expect(item.descricao).toBe('Leitura por agente com o token jp_abc1234: processos/7/andamentos/ (HTTP 200).');
  });

  it('descreve o acesso negado de forma distinta da leitura', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [evento('token_api.negado', {
      credencial: 'jp_abc1234', caminho: 'clientes/', status: 403,
    })] });

    const [item] = await auditoriaService.list();

    expect(item.descricao).toBe('Acesso negado ao token jp_abc1234: clientes/ (HTTP 403).');
  });

  it('lista os campos alterados, e não o nome da chave que os guarda', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [evento('processo.atualizado', { campos: ['titulo', 'status'] })] });

    const [item] = await auditoriaService.list();

    expect(item.descricao).toBe('Campos alterados: titulo, status.');
  });

  it('usa as chaves quando o evento registra os valores de cada campo', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: [evento('membro.atualizado', { papel: { anterior: 'ADVOGADO', novo: 'ADMIN' } })] });

    const [item] = await auditoriaService.list();

    expect(item.descricao).toBe('Campos alterados: papel.');
  });
});
