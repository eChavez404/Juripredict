import api from './api';
import type {
  AndamentosResposta,
  Cliente,
  ClientePayload,
  DashboardData,
  DocumentoProcesso,
  EventoAgenda,
  JurimetriaData,
  JurimetriaProcessos,
  Pendencias,
  PrazoCalculado,
  PrazoTipo,
  Processo,
  Usuario,
} from '../types';

export const authService = {
  login: async (username: string, password: string) => (
    await api.post<{ access: string; refresh: string; user: Usuario }>('/auth/token/', { username, password })
  ).data,
  // Revoga o refresh token no servidor. Não exige login: quem sai com o access
  // token já expirado também precisa conseguir encerrar a sessão.
  logout: async (refresh: string) => {
    await api.post('/auth/logout/', { refresh });
  },
  me: async () => (await api.get<unknown>('/auth/me/')).data,
  updateMe: async (payload: Pick<Usuario, 'nome' | 'email'>) => (
    await api.patch<Usuario>('/auth/me/', payload)
  ).data,
  changePassword: async (senha_atual: string, nova_senha: string) => (
    await api.post<{ detail: string }>('/auth/password/', { senha_atual, nova_senha })
  ).data,
};

export const clienteService = {
  list: async () => (await api.get<Cliente[]>('/clientes/')).data,
  create: async (payload: ClientePayload) => (await api.post<Cliente>('/clientes/', payload)).data,
  update: async (id: number, payload: ClientePayload) => (
    await api.put<Cliente>(`/clientes/${id}/`, payload)
  ).data,
  remove: async (id: number) => api.delete(`/clientes/${id}/`),
};

export const processoService = {
  list: async () => (await api.get<Processo[]>('/processos/')).data,
  save: async (payload: FormData, id?: number) => (
    id
      ? (await api.patch<Processo>(`/processos/${id}/`, payload)).data
      : (await api.post<Processo>('/processos/', payload)).data
  ),
  remove: async (id: number) => api.delete(`/processos/${id}/`),
  documentos: async (id: number) => (
    await api.get<DocumentoProcesso[]>(`/processos/${id}/documentos/`)
  ).data,
  anexarDocumento: async (id: number, arquivo: File) => {
    const payload = new FormData();
    payload.append('arquivo', arquivo);
    return (await api.post<DocumentoProcesso>(`/processos/${id}/documentos/`, payload)).data;
  },
  removerDocumento: async (id: number, documentoId: number) => {
    await api.delete(`/processos/${id}/documentos/${documentoId}/`);
  },
  andamentos: async (id: number) => (
    await api.get<AndamentosResposta>(`/processos/${id}/andamentos/`)
  ).data,
  sincronizarAndamentos: async (id: number) => (
    await api.post<AndamentosResposta & { novos: number }>(`/processos/${id}/andamentos/sincronizar/`)
  ).data,
};

export const eventoService = {
  list: async (inicio?: string, fim?: string) => (
    await api.get<EventoAgenda[]>('/eventos/', { params: { inicio, fim } })
  ).data,
  create: async (payload: Record<string, unknown>) => (
    await api.post<EventoAgenda>('/eventos/', payload)
  ).data,
  update: async (id: number, payload: Record<string, unknown>) => (
    await api.patch<EventoAgenda>(`/eventos/${id}/`, payload)
  ).data,
  remove: async (id: number) => api.delete(`/eventos/${id}/`),
};

export const dashboardService = {
  get: async () => (await api.get<DashboardData>('/dashboard/')).data,
};

export type FiltrosJurimetria = { area?: string; ano?: string; vara?: string; resultado?: string };

// Campos vazios ficam fora da URL: `?area=` seria um filtro por área em branco.
const semVazios = (filtros: FiltrosJurimetria) => Object.fromEntries(
  Object.entries(filtros).filter(([, valor]) => valor),
);

export const jurimetriaService = {
  get: async (filtros: FiltrosJurimetria = {}) => (
    await api.get<JurimetriaData>('/jurimetria/', { params: semVazios(filtros) })
  ).data,
  processos: async (filtros: FiltrosJurimetria = {}) => (
    await api.get<JurimetriaProcessos>('/jurimetria/processos/', { params: semVazios(filtros) })
  ).data,
  exportar: async (filtros: FiltrosJurimetria = {}) => {
    const { data } = await api.get<Blob>('/jurimetria/exportar/', {
      params: semVazios(filtros),
      responseType: 'blob',
    });
    const url = URL.createObjectURL(data);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'jurimetria-carteira.csv';
    link.click();
    URL.revokeObjectURL(url);
  },
};

export const prazoService = {
  calcular: async (params: {
    data_base: string; dias: number; tipo: PrazoTipo; area: string; suspensoes: string[];
  }) => (
    await api.get<PrazoCalculado>('/prazos/calcular/', {
      params,
      // repete a chave (`suspensoes=a&suspensoes=b`), que é o que a API entende
      paramsSerializer: { indexes: null },
    })
  ).data,
};

export const pendenciaService = {
  get: async () => (await api.get<Pendencias>('/pendencias/')).data,
};
