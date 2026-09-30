import { createContext, useContext } from 'react';
import type { Usuario } from '../types';

export type AuthContextValue = {
  user: Usuario | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  updateUser: (user: Usuario) => void;
  logout: () => void;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth deve ser usado dentro de AuthProvider.');
  return context;
};
