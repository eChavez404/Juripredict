import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { SessaoResposta } from '../features/conta/types';
import { normalizeSessao, resolveEscritorioAtivo } from '../features/escritorios/sessionAdapter';
import { getStoredEscritorioId, setStoredEscritorioId } from '../features/escritorios/storage';
import type { Capability, MembroResumo } from '../features/escritorios/types';
import { authService } from '../services/juripredict';
import type { Usuario } from '../types';
import { AuthContext, type AuthContextValue } from './auth';

const persistSession = (result: SessaoResposta) => {
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
    // Melhor esforço: se a rede falhar, a sessão local encerra do mesmo jeito.
    const refresh = localStorage.getItem('refresh_token');
    if (refresh) void authService.logout(refresh).catch(() => undefined);
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

  // Abre a sessão a partir de tokens já emitidos. É o que o login, o cadastro e
  // o aceite de convite têm em comum: só mudam em como os tokens são obtidos.
  const startSession = useCallback(async (result: SessaoResposta) => {
    setStoredEscritorioId(null);
    try {
      persistSession(result);
      const session = await authService.me();
      applySession(session, result.user);
    } catch (error) {
      logout();
      throw error;
    }
  }, [applySession, logout]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    memberships,
    capabilities,
    activeEscritorio: activeMembership?.escritorio ?? null,
    activeMembership,
    loading,
    login: async (username, password) => {
      setStoredEscritorioId(null);
      let result: SessaoResposta;
      try {
        result = await authService.login(username, password);
      } catch (error) {
        logout();
        throw error;
      }
      await startSession(result);
    },
    startSession,
    updateUser: (updatedUser) => {
      setUser(updatedUser);
      localStorage.setItem('juripredict_user', JSON.stringify(updatedUser));
    },
    selectEscritorio,
    hasCapability: (capability) => capabilities.includes(capability),
    logout,
  }), [
    activeMembership,
    capabilities,
    loading,
    logout,
    memberships,
    selectEscritorio,
    startSession,
    user,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
