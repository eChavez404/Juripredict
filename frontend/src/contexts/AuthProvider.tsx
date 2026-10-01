import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { normalizeSessao, resolveEscritorioAtivo } from '../features/escritorios/sessionAdapter';
import { getStoredEscritorioId, setStoredEscritorioId } from '../features/escritorios/storage';
import type { Capability, MembroResumo } from '../features/escritorios/types';
import { authService } from '../services/juripredict';
import type { Usuario } from '../types';
import { AuthContext, type AuthContextValue } from './auth';

type AuthResult = { access: string; refresh: string; user: Usuario };

const persistSession = (result: AuthResult) => {
  localStorage.setItem('access_token', result.access);
  localStorage.setItem('refresh_token', result.refresh);
  localStorage.setItem('juripredict_user', JSON.stringify(result.user));
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<Usuario | null>(() => {
    try {
      const saved = localStorage.getItem('juripredict_user');
      return saved ? JSON.parse(saved) as Usuario : null;
    } catch {
      return null;
    }
  });
  const [memberships, setMemberships] = useState<MembroResumo[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [activeMembership, setActiveMembership] = useState<MembroResumo | null>(null);
  const [loading, setLoading] = useState(Boolean(localStorage.getItem('access_token')));

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('juripredict_user');
    setStoredEscritorioId(null);
    setUser(null);
    setMemberships([]);
    setCapabilities([]);
    setActiveMembership(null);
  }, []);

  const applySession = useCallback((payload: unknown, fallbackUser?: Usuario) => {
    const session = normalizeSessao(payload, fallbackUser);
    const preferredId = session.escritorioAtivo?.id ?? getStoredEscritorioId();
    const active = resolveEscritorioAtivo(session.memberships, preferredId);

    setUser(session.usuario);
    setMemberships(session.memberships);
    setCapabilities(active ? session.capabilities : []);
    setActiveMembership(active);
    setStoredEscritorioId(active?.escritorio.id ?? null);
    localStorage.setItem('juripredict_user', JSON.stringify(session.usuario));
  }, []);

  useEffect(() => {
    if (!localStorage.getItem('access_token')) return;
    authService.me()
      .then((session) => applySession(session))
      .catch(logout)
      .finally(() => setLoading(false));
  }, [applySession, logout]);

  const selectEscritorio = useCallback(async (escritorioId: string) => {
    const membership = memberships.find((item) => (
      item.escritorio.id === escritorioId && item.status === 'ATIVO'
    ));
    if (!membership) throw new Error('Escritório indisponível para esta conta.');
    if (activeMembership?.escritorio.id === escritorioId) return;

    const previousId = activeMembership?.escritorio.id ?? null;
    setStoredEscritorioId(escritorioId);
    try {
      const session = await authService.me();
      applySession(session, user ?? undefined);
    } catch (error) {
      setStoredEscritorioId(previousId);
      throw error;
    }
  }, [activeMembership, applySession, memberships, user]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    memberships,
    capabilities,
    activeEscritorio: activeMembership?.escritorio ?? null,
    activeMembership,
    loading,
    login: async (username, password) => {
      setStoredEscritorioId(null);
      try {
        const result = await authService.login(username, password);
        persistSession(result);
        const session = await authService.me();
        applySession(session, result.user);
      } catch (error) {
        logout();
        throw error;
      }
    },
    updateUser: (updatedUser) => {
      setUser(updatedUser);
      localStorage.setItem('juripredict_user', JSON.stringify(updatedUser));
    },
    selectEscritorio,
    hasCapability: (capability) => capabilities.includes(capability),
    logout,
  }), [
    activeMembership,
    applySession,
    capabilities,
    loading,
    logout,
    memberships,
    selectEscritorio,
    user,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
