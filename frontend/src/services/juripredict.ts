import api from './api';
import type {
  Cliente,
  ClientePayload,
  DashboardData,
  EventoAgenda,
  JurimetriaData,
  Processo,
  Usuario,
} from '../types';

export const authService = {
  login: async (username: string, password: string) => (
    await api.post<{ access: string; refresh: string; user: Usuario }>('/auth/token/', { username, password })
  ).data,
  me: async () => (await api.get<Usuario>('/auth/me/')).data,
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

export const jurimetriaService = {
  get: async () => (await api.get<JurimetriaData>('/jurimetria/')).data,
};
