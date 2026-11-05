import api from '../../services/api';
import type { Usuario } from '../../types';
import type { Convite, MembroResumo, PapelMembro, StatusMembro } from './types';
import { normalizeSessao } from './sessionAdapter';

type CollectionResponse<T> = T[] | { results?: T[] };

const collectionItems = <T,>(payload: CollectionResponse<T>): T[] => (
  Array.isArray(payload) ? payload : payload.results ?? []
);

const normalizeMembro = (value: unknown): MembroResumo | null => {
  const sessao = normalizeSessao({
    usuario: {},
    memberships: [value],
  });
  return sessao.memberships[0] ?? null;
};

export const equipeService = {
  list: async (escritorioId: string) => {
    const response = await api.get<CollectionResponse<unknown>>(`/escritorios/${escritorioId}/membros/`);
    return collectionItems(response.data)
      .map(normalizeMembro)
      .filter((item): item is MembroResumo => item !== null);
  },
  update: async (
    escritorioId: string,
    membroId: string,
    payload: Partial<{ papel: PapelMembro; status: StatusMembro }>,
  ) => {
    const response = await api.patch<unknown>(
      `/escritorios/${escritorioId}/membros/${membroId}/`,
      payload,
    );
    return normalizeMembro(response.data);
  },
};

export const conviteService = {
  list: async (escritorioId: string) => collectionItems(
    (await api.get<CollectionResponse<Convite>>(`/escritorios/${escritorioId}/convites/`)).data,
  ),
  create: async (escritorioId: string, payload: { email: string; papel: PapelMembro }) => (
    await api.post<Convite>(`/escritorios/${escritorioId}/convites/`, payload)
  ).data,
  revoke: async (escritorioId: string, conviteId: string) => {
    await api.delete(`/escritorios/${escritorioId}/convites/${conviteId}/`);
  },
};

export const usuarioDoMembro = (membro: MembroResumo): Usuario => membro.usuario;
