import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { getStoredEscritorioId, setStoredEscritorioId } from '../features/escritorios/storage';

export const API_URL = import.meta.env.VITE_API_URL ?? '/api/v1';

type RetryableRequest = InternalAxiosRequestConfig & { _retry?: boolean };

const api = axios.create({
  baseURL: API_URL,
  timeout: 15000,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  const escritorioId = getStoredEscritorioId();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (escritorioId) {
    config.headers['X-Escritorio-ID'] = String(escritorioId);
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequest | undefined;
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/token/');

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const response = await axios.post<{ access: string }>(`${API_URL}/auth/token/refresh/`, {
            refresh: refreshToken,
          });
          localStorage.setItem('access_token', response.data.access);
          originalRequest.headers.Authorization = `Bearer ${response.data.access}`;
          return api(originalRequest);
        } catch {
          // O fluxo abaixo encerra a sessão quando o refresh não é mais válido.
        }
      }

      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('juripredict_user');
      setStoredEscritorioId(null);
      if (window.location.pathname !== '/login') {
        window.location.assign('/login');
      }
    }
    return Promise.reject(error);
  },
);

export const getApiError = (error: unknown): string => {
  if (!axios.isAxiosError(error)) return 'Não foi possível concluir a operação.';

  const data = error.response?.data;
  if (typeof data === 'string') return data;
  if (data && typeof data === 'object') {
    const record = data as Record<string, unknown>;
    if (typeof record.detail === 'string') return record.detail;
    const first = Object.values(record)[0];
    if (Array.isArray(first) && first.length) return String(first[0]);
    if (typeof first === 'string') return first;
  }
  if (error.code === 'ERR_NETWORK') {
    return 'Não foi possível conectar ao backend. Confirme se ele está rodando na porta 8000.';
  }
  return 'Não foi possível concluir a operação.';
};

export default api;
