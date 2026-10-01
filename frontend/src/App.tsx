import { lazy, Suspense, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import { useAuth } from './contexts/auth';

const Login = lazy(() => import('./pages/Login'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Processos = lazy(() => import('./pages/Processos'));
const Clientes = lazy(() => import('./pages/Clientes'));
const Agenda = lazy(() => import('./pages/Agenda'));
const Jurimetria = lazy(() => import('./pages/Jurimetria'));
const Configuracoes = lazy(() => import('./pages/Configuracoes'));
const Equipe = lazy(() => import('./pages/Equipe'));
const Auditoria = lazy(() => import('./pages/Auditoria'));

const PrivateRoute = ({ children }: { children: ReactNode }) => {
  const { user, loading } = useAuth();
  if (loading) return <div className="route-loader" role="status" aria-label="Carregando" />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
};

const PublicRoute = ({ children }: { children: ReactNode }) => {
  const { user, loading } = useAuth();
  if (loading) return <div className="route-loader" role="status" aria-label="Carregando" />;
  return user ? <Navigate to="/" replace /> : <>{children}</>;
};

const App = () => (
  <BrowserRouter>
    <Suspense fallback={<div className="route-loader" role="status" aria-label="Carregando" />}>
      <Routes>
        <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />

        <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
          <Route index element={<Dashboard />} />
          <Route path="processos" element={<Processos />} />
          <Route path="clientes" element={<Clientes />} />
          <Route path="agenda" element={<Agenda />} />
          <Route path="jurimetria" element={<Jurimetria />} />
          <Route path="configuracoes" element={<Configuracoes />} />
          <Route path="configuracoes/equipe" element={<Equipe />} />
          <Route path="configuracoes/auditoria" element={<Auditoria />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  </BrowserRouter>
);

export default App;
