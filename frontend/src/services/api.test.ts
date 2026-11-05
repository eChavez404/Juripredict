import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ACTIVE_ESCRITORIO_STORAGE_KEY } from '../features/escritorios/storage';
import api from './api';

describe('cliente HTTP', () => {
  afterEach(() => localStorage.clear());

  it('envia o escritório ativo no cabeçalho das requisições', async () => {
    localStorage.setItem(ACTIVE_ESCRITORIO_STORAGE_KEY, '42');
    let escritorioHeader: unknown;

    await api.get('/probe', {
      adapter: async (config) => {
        escritorioHeader = config.headers.get('X-Escritorio-ID');
        return ({
        data: null,
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      });
      },
    });

    expect(escritorioHeader).toBe('42');
  });

  it('guarda o refresh token rotacionado ao renovar a sessão', async () => {
    localStorage.setItem('access_token', 'a-velho');
    localStorage.setItem('refresh_token', 'r-velho');
    const renovar = vi.spyOn(axios, 'post').mockResolvedValue({
      data: { access: 'a-novo', refresh: 'r-novo' },
    });
    let chamadas = 0;

    const resposta = await api.get('/protegido', {
      adapter: async (config: InternalAxiosRequestConfig) => {
        chamadas += 1;
        if (chamadas === 1) {
          throw new AxiosError('expirou', 'ERR_BAD_REQUEST', config, null, {
            status: 401, statusText: 'Unauthorized', headers: {}, config, data: null,
          });
        }
        return { data: { ok: true }, status: 200, statusText: 'OK', headers: {}, config };
      },
    });

    expect(resposta.data).toEqual({ ok: true });
    expect(localStorage.getItem('access_token')).toBe('a-novo');
    // com a rotação ligada o refresh antigo é invalidado: sem guardar o novo, a
    // próxima renovação falharia e a pessoa seria deslogada
    expect(localStorage.getItem('refresh_token')).toBe('r-novo');
    expect(renovar).toHaveBeenCalledWith(expect.stringContaining('/auth/token/refresh/'), {
      refresh: 'r-velho',
    });
    renovar.mockRestore();
  });

  const expirouUmaVez = () => {
    const expirados = new Set<string>();
    return async (config: InternalAxiosRequestConfig) => {
      if (config.headers.get('Authorization') === 'Bearer a-velho' && !expirados.has(String(config.url))) {
        expirados.add(String(config.url));
        throw new AxiosError('expirou', 'ERR_BAD_REQUEST', config, null, {
          status: 401, statusText: 'Unauthorized', headers: {}, config, data: null,
        });
      }
      return { data: config.url, status: 200, statusText: 'OK', headers: {}, config };
    };
  };

  it('faz uma única renovação quando várias chamadas expiram juntas', async () => {
    localStorage.setItem('access_token', 'a-velho');
    localStorage.setItem('refresh_token', 'r-velho');
    // como o servidor com rotação: o mesmo refresh só é aceito uma vez
    const usados = new Set<string>();
    const renovar = vi.spyOn(axios, 'post').mockImplementation(async (_url, corpo) => {
      const { refresh } = corpo as { refresh: string };
      await new Promise((resolver) => setTimeout(resolver, 5));
      if (usados.has(refresh)) throw new AxiosError('refresh revogado');
      usados.add(refresh);
      return { data: { access: 'a-novo', refresh: 'r-novo' } };
    });
    const adapter = expirouUmaVez();

    const respostas = await Promise.all(['/um', '/dois', '/tres'].map((url) => api.get(url, { adapter })));

    expect(respostas.map((resposta) => resposta.data)).toEqual(['/um', '/dois', '/tres']);
    expect(renovar).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('refresh_token')).toBe('r-novo');
    renovar.mockRestore();
  });

  it('não encerra a sessão quando outra aba já renovou com o mesmo refresh', async () => {
    localStorage.setItem('access_token', 'a-velho');
    localStorage.setItem('refresh_token', 'r-velho');
    const renovar = vi.spyOn(axios, 'post').mockImplementation(async () => {
      localStorage.setItem('access_token', 'a-da-outra-aba');
      localStorage.setItem('refresh_token', 'r-da-outra-aba');
      throw new AxiosError('refresh revogado');
    });

    const resposta = await api.get('/protegido', { adapter: expirouUmaVez() });

    expect(resposta.data).toBe('/protegido');
    expect(localStorage.getItem('refresh_token')).toBe('r-da-outra-aba');
    renovar.mockRestore();
  });

  it('encerra a sessão quando o refresh foi mesmo recusado', async () => {
    localStorage.setItem('access_token', 'a-velho');
    localStorage.setItem('refresh_token', 'r-velho');
    const renovar = vi.spyOn(axios, 'post').mockRejectedValue(new AxiosError('refresh revogado'));

    await expect(api.get('/protegido', { adapter: expirouUmaVez() })).rejects.toBeInstanceOf(AxiosError);

    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    renovar.mockRestore();
  });
});
