import api from '../../services/api';
import type { EventoAuditoria } from './types';

type UnknownRecord = Record<string, unknown>;
type CollectionResponse<T> = T[] | { results?: T[] };

const isRecord = (value: unknown): value is UnknownRecord => (
  Boolean(value) && typeof value === 'object' && !Array.isArray(value)
);

const asString = (value: unknown, fallback = '') => (
  typeof value === 'string' ? value : fallback
);

const collectionItems = <T,>(payload: CollectionResponse<T>): T[] => (
  Array.isArray(payload) ? payload : payload.results ?? []
);

const normalizeEvento = (value: unknown): EventoAuditoria | null => {
  if (!isRecord(value)) return null;
  const rawId = typeof value.id === 'string' ? value.id : String(value.id ?? '');
  if (!rawId) return null;

  const ator = isRecord(value.ator ?? value.actor) ? value.ator ?? value.actor : {};
  const recurso = isRecord(value.recurso ?? value.resource) ? value.recurso ?? value.resource : {};
  const ocorridoEm = asString(value.ocorrido_em ?? value.occurred_at ?? value.criado_em);
  const alteracoes = isRecord(value.alteracoes) ? Object.keys(value.alteracoes) : [];

  return {
    id: rawId,
    acao: asString(value.acao ?? value.action, 'EVENTO').replaceAll('_', ' '),
    descricao: asString(
      value.descricao ?? value.summary ?? value.detail,
      alteracoes.length ? `Campos alterados: ${alteracoes.join(', ')}.` : 'Ação registrada.',
    ),
    atorNome: asString(value.ator_nome) || (isRecord(ator)
      ? asString(ator.nome ?? ator.name ?? ator.email, 'Sistema')
      : 'Sistema'),
    recurso: isRecord(recurso)
      ? asString(recurso.label ?? recurso.tipo ?? recurso.type, 'Registro')
      : [asString(value.recurso_tipo, 'Registro'), asString(value.recurso_id)].filter(Boolean).join(' · '),
    ocorridoEm,
  };
};

/** Adapta temporariamente aliases até o schema OpenAPI do endpoint ser fechado. */
export const auditoriaService = {
  list: async () => {
    const response = await api.get<CollectionResponse<unknown>>('/auditoria/');
    return collectionItems(response.data)
      .map(normalizeEvento)
      .filter((item): item is EventoAuditoria => item !== null);
  },
};
