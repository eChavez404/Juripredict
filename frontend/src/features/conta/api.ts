import api from '../../services/api';
import type {
  AceitarConvitePayload,
  ConfirmarResetPayload,
  CriarTokenPayload,
  RegistroPayload,
  SessaoResposta,
  TokenApi,
  TokenApiCriado,
} from './types';

export const contaService = {
  registrar: async (payload: RegistroPayload) => (
    await api.post<SessaoResposta>('/auth/register/', payload)
  ).data,
  aceitarConvite: async (payload: AceitarConvitePayload) => (
    await api.post<SessaoResposta>('/auth/convites/aceitar/', payload)
  ).data,
  solicitarReset: async (email: string) => (
    await api.post<{ detail: string }>('/auth/password/reset/', { email })
  ).data,
  exportarDados: async () => (
    await api.get<Blob>('/auth/me/exportar/', { responseType: 'blob' })
  ).data,
  excluirConta: async (senha: string) => {
    await api.post('/auth/me/excluir/', { senha });
  },
  listarTokens: async () => (await api.get<TokenApi[]>('/auth/tokens/')).data,
  criarToken: async (payload: CriarTokenPayload) => (
    await api.post<TokenApiCriado>('/auth/tokens/', payload)
  ).data,
  revogarToken: async (id: number) => {
    await api.delete(`/auth/tokens/${id}/`);
  },
  confirmarEmail: async (token: string) => (
    await api.post<{ detail: string }>('/auth/email/confirmar/', { token })
  ).data,
  reenviarVerificacao: async () => (
    await api.post<{ detail: string }>('/auth/email/reenviar/')
  ).data,
  confirmarReset: async (payload: ConfirmarResetPayload) => (
    await api.post<{ detail: string }>('/auth/password/reset/confirm/', payload)
  ).data,
};
