import type { Usuario } from '../../types';
import type {
  Capability,
  EscritorioResumo,
  MembroResumo,
  PapelMembro,
  Sessao,
  StatusMembro,
} from './types';

type UnknownRecord = Record<string, unknown>;

const isRecord = (value: unknown): value is UnknownRecord => (
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)
);

const asString = (value: unknown, fallback = '') => (
  typeof value === 'string' ? value : fallback
);

const asNumber = (value: unknown): number | null => {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
};

const asId = (value: unknown): string | null => {
  if (typeof value === 'string' && value.trim()) return value;
  if (typeof value === 'number' && Number.isSafeInteger(value)) return String(value);
  return null;
};

const normalizeUsuario = (value: unknown, fallback?: Usuario): Usuario => {
  const source = isRecord(value) ? value : {};
  return {
    id: asNumber(source.id) ?? fallback?.id ?? 0,
    username: asString(source.username, fallback?.username ?? ''),
    email: asString(source.email, fallback?.email ?? ''),
    nome: asString(source.nome ?? source.name, fallback?.nome ?? ''),
  };
};

const normalizeEscritorio = (value: unknown): EscritorioResumo | null => {
  if (!isRecord(value)) return null;
  const id = asId(value.id);
  if (!id) return null;
  return {
    id,
    nome: asString(value.nome ?? value.name, `Escritório ${id}`),
    fuso_horario: asString(value.fuso_horario ?? value.timezone, 'America/Sao_Paulo'),
  };
};

const normalizeCapabilities = (value: unknown): Capability[] => (
  Array.isArray(value)
    ? [...new Set(value.filter((item): item is string => typeof item === 'string'))]
    : []
);

const normalizeMembership = (value: unknown, fallbackUser: Usuario): MembroResumo | null => {
  if (!isRecord(value)) return null;

  const escritorio = normalizeEscritorio(value.escritorio ?? value.organization);
  const id = asId(value.id);
  if (!escritorio || !id) return null;

  return {
    id,
    usuario: normalizeUsuario(value.usuario ?? value.user, fallbackUser),
    escritorio,
    papel: asString(value.papel ?? value.role, 'ESTAGIARIO').toUpperCase() as PapelMembro,
    status: asString(value.status, 'ATIVO').toUpperCase() as StatusMembro,
    criado_em: asString(value.criado_em ?? value.created_at),
    atualizado_em: asString(value.atualizado_em ?? value.updated_at),
  };
};

/**
 * Único ponto de compatibilidade com o contrato de sessão do backend. Quando o
 * schema OpenAPI estiver estabilizado, os aliases em inglês podem ser removidos.
 */
export const normalizeSessao = (payload: unknown, fallbackUser?: Usuario): Sessao => {
  const source = isRecord(payload) ? payload : {};
  const usuario = normalizeUsuario(source.usuario ?? source.user ?? source, fallbackUser);
  const rawMemberships = source.memberships ?? source.membros;
  const memberships = Array.isArray(rawMemberships)
    ? rawMemberships
      .map((item) => normalizeMembership(item, usuario))
      .filter((item): item is MembroResumo => item !== null)
    : [];

  return {
    usuario,
    memberships,
    escritorioAtivo: normalizeEscritorio(source.escritorio_ativo ?? source.active_organization),
    capabilities: normalizeCapabilities(source.capabilities ?? source.permissoes),
  };
};

export const resolveEscritorioAtivo = (
  memberships: MembroResumo[],
  storedId: string | null,
): MembroResumo | null => {
  const ativos = memberships.filter((membership) => membership.status === 'ATIVO');
  const storedMembership = ativos.find((membership) => membership.escritorio.id === storedId);
  if (storedMembership) return storedMembership;
  return ativos.length === 1 ? ativos[0] : null;
};
