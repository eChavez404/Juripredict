import type { Usuario } from '../../types';

export const CAPABILITIES = {
  membrosVisualizar: 'membros.ler',
  membrosGerenciar: 'membros.gerenciar',
  auditoriaVisualizar: 'auditoria.ler',
} as const;

export type Capability = string;

export type PapelMembro =
  | 'OWNER'
  | 'ADMIN'
  | 'ADVOGADO'
  | 'ESTAGIARIO';

export type StatusMembro = 'ATIVO' | 'SUSPENSO';

export type EscritorioResumo = {
  id: string;
  nome: string;
  fuso_horario: string;
};

export type MembroResumo = {
  id: string;
  usuario: Usuario;
  escritorio: EscritorioResumo;
  papel: PapelMembro;
  status: StatusMembro;
  criado_em: string;
  atualizado_em: string;
};

export type Sessao = {
  usuario: Usuario;
  memberships: MembroResumo[];
  escritorioAtivo: EscritorioResumo | null;
  capabilities: Capability[];
};

export const papelLabels: Record<PapelMembro, string> = {
  OWNER: 'Proprietário',
  ADMIN: 'Administrador',
  ADVOGADO: 'Advogado',
  ESTAGIARIO: 'Estagiário',
};

export const statusMembroLabels: Record<StatusMembro, string> = {
  ATIVO: 'Ativo',
  SUSPENSO: 'Suspenso',
};

export const papeisDisponiveis = Object.keys(papelLabels) as PapelMembro[];
