import type { Usuario } from '../../types';

export type SessaoResposta = { access: string; refresh: string; user: Usuario };

export type RegistroPayload = {
  nome: string;
  email: string;
  senha: string;
  escritorio_nome: string;
  aceite_termos: boolean;
};

export type AceitarConvitePayload = {
  token: string;
  senha: string;
  nome?: string;
  aceite_termos?: boolean;
};

export type TokenApi = {
  id: number;
  nome: string;
  prefixo: string;
  criado_em: string;
  expira_em: string;
  ultimo_uso_em: string | null;
  revogado_em: string | null;
  ativo: boolean;
};

/** Resposta da criação: o texto do token só existe aqui, nunca mais. */
export type TokenApiCriado = TokenApi & { token: string };

export type CriarTokenPayload = { nome: string; senha: string; validade_dias?: number };

export type ConfirmarResetPayload = { uid: string; token: string; nova_senha: string };
