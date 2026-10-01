import { createContext, useContext } from 'react';
import type { Capability, EscritorioResumo, MembroResumo } from '../features/escritorios/types';
import type { Usuario } from '../types';

export type AuthContextValue = {
  user: Usuario | null;
  memberships: MembroResumo[];
  capabilities: Capability[];
  activeEscritorio: EscritorioResumo | null;
  activeMembership: MembroResumo | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  updateUser: (user: Usuario) => void;
  selectEscritorio: (escritorioId: string) => Promise<void>;
  hasCapability: (capability: Capability) => boolean;
  logout: () => void;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth deve ser usado dentro de AuthProvider.');
  return context;
};
