import { lazy, Suspense, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes, useLocation, type Location } from 'react-router-dom';
import Layout from './components/Layout';
import { useAuth } from './contexts/auth';

const Login = lazy(() => import('./pages/Login'));
const Registro = lazy(() => import('./pages/Registro'));
const EsqueciSenha = lazy(() => import('./pages/EsqueciSenha'));
const RedefinirSenha = lazy(() => import('./pages/RedefinirSenha'));
const ConfirmarEmail = lazy(() => import('./pages/ConfirmarEmail'));
const AceitarConvite = lazy(() => import('./pages/AceitarConvite'));
const Termos = lazy(() => import('./pages/Termos'));
const Privacidade = lazy(() => import('./pages/Privacidade'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Processos = lazy(() => import('./pages/Processos'));
const Clientes = lazy(() => import('./pages/Clientes'));
const Agenda = lazy(() => import('./pages/Agenda'));
const Jurimetria = lazy(() => import('./pages/Jurimetria'));
const Agente = lazy(() => import('./pages/Agente'));
const Configuracoes = lazy(() => import('./pages/Configuracoes'));
const Equipe = lazy(() => import('./pages/Equipe'));
const Auditoria = lazy(() => import('./pages/Auditoria'));
const Autorizar = lazy(() => import('./pages/Autorizar'));

const PrivateRoute = ({ children }: { children: ReactNode }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="route-loader" role="status" aria-label="Carregando" />;
  // Guarda a página pedida para o login voltar a ela: a tela /autorizar depende disso.
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return <>{children}</>;
};

const PublicRoute = ({ children }: { children: ReactNode }) => {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="route-loader" role="status" aria-label="Carregando" />;
  const destino = (location.state as { from?: Location } | null)?.from ?? '/';
  return user ? <Navigate to={destino} replace /> : <>{children}</>;
};

const App = () => (
  <BrowserRouter>
    <Suspense fallback={<div className="route-loader" role="status" aria-label="Carregando" />}>
      <Routes>
        <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
        <Route path="/registro" element={<PublicRoute><Registro /></PublicRoute>} />
        <Route path="/esqueci-senha" element={<PublicRoute><EsqueciSenha /></PublicRoute>} />
        {/* Links de e-mail: abrem mesmo com outra conta logada no navegador. */}
        <Route path="/redefinir-senha" element={<RedefinirSenha />} />
        <Route path="/confirmar-email" element={<ConfirmarEmail />} />
        <Route path="/convite"element={<AceitarConvite />} />
        <Route path="/termos" element={<Termos />} />
        <Route path="/privacidade" element={<Privacidade />} />
        {/* Consentimento do conector MCP remoto (OAuth): fora do layout do app. */}
        <Route path="/autorizar" element={<PrivateRoute><Autorizar /></PrivateRoute>} />

        <Route path="/" element={<PrivateRoute><Layout /></PrivateRoute>}>
          <Route index element={<Dashboard />} />
          <Route path="processos" element={<Processos />} />
          <Route path="clientes" element={<Clientes />} />
          <Route path="agenda" element={<Agenda />} />
          <Route path="jurimetria" element={<Jurimetria />} />
          <Route path="agente" element={<Agente />} />
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
