import { useEffect, useMemo, useState, type ReactNode } from 'react';
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
  const [loading, setLoading] = useState(Boolean(localStorage.getItem('access_token')));

  const logout = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('juripredict_user');
    setUser(null);
  };

  useEffect(() => {
    if (!localStorage.getItem('access_token')) return;
    authService.me()
      .then((currentUser) => {
        setUser(currentUser);
        localStorage.setItem('juripredict_user', JSON.stringify(currentUser));
      })
      .catch(logout)
      .finally(() => setLoading(false));
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    login: async (username, password) => {
      const result = await authService.login(username, password);
      persistSession(result);
      setUser(result.user);
    },
    updateUser: (updatedUser) => {
      setUser(updatedUser);
      localStorage.setItem('juripredict_user', JSON.stringify(updatedUser));
    },
    logout,
  }), [loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
