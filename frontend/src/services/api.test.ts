import { afterEach, describe, expect, it } from 'vitest';
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
});
