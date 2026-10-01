import { useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  CalendarDays,
  FileText,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  TrendingUp,
  Users,
} from 'lucide-react';
import { useAuth } from '../contexts/auth';
import EscritorioSelector from '../features/escritorios/EscritorioSelector';
import Brand from './ui/Brand';

const navItems = [
  { label: 'Visão geral', icon: LayoutDashboard, path: '/' },
  { label: 'Processos', icon: FileText, path: '/processos' },
  { label: 'Clientes', icon: Users, path: '/clientes' },
  { label: 'Agenda e prazos', icon: CalendarDays, path: '/agenda' },
  { label: 'Jurimetria', icon: TrendingUp, path: '/jurimetria' },
];

const pageLabels: Record<string, string> = {
  '/': 'Visão geral do escritório',
  '/processos': 'Gestão de processos',
  '/clientes': 'Relacionamento com clientes',
  '/agenda': 'Agenda e prazos',
  '/jurimetria': 'Inteligência e jurimetria',
  '/configuracoes': 'Configurações da conta',
  '/configuracoes/equipe': 'Equipe e permissões',
  '/configuracoes/auditoria': 'Trilha de auditoria',
};

const Layout = () => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const goTo = (path: string) => {
    navigate(path);
    setSidebarOpen(false);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const displayName = user?.nome || user?.username || 'Usuário';
  const initials = displayName
    .split(' ')
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();

  return (
    <div className="app-shell">
      {sidebarOpen && (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="Fechar menu"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <aside className={`sidebar${sidebarOpen ? ' sidebar--open' : ''}`} aria-label="Navegação principal">
        <div className="sidebar__brand"><Brand /></div>
        <span className="sidebar__section-label">Menu principal</span>

        <nav className="sidebar__nav">
          {navItems.map((item) => {
            const isActive = item.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(item.path);

            return (
              <button
                key={item.path}
                type="button"
                className={`sidebar__link${isActive ? ' sidebar__link--active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => goTo(item.path)}
              >
                <item.icon size={18} strokeWidth={1.8} aria-hidden="true" />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="sidebar__bottom">
          <button
            className={`sidebar__link${location.pathname === '/configuracoes' ? ' sidebar__link--active' : ''}`}
            type="button"
            onClick={() => goTo('/configuracoes')}
          >
            <Settings size={18} strokeWidth={1.8} aria-hidden="true" />
            Configurações
          </button>
          <button className="sidebar__link sidebar__link--danger" type="button" onClick={handleLogout}>
            <LogOut size={18} strokeWidth={1.8} aria-hidden="true" />
            Sair do sistema
          </button>
        </div>
      </aside>

      <main className="app-main">
        <header className="topbar">
          <button
            className="menu-button"
            type="button"
            aria-label="Abrir menu"
            aria-expanded={sidebarOpen}
            onClick={() => setSidebarOpen(true)}
          >
            <Menu size={20} />
          </button>

          <div className="topbar__context">
            <span>JuriPredict</span>
            <strong>{pageLabels[location.pathname] ?? 'Gestão jurídica'}</strong>
          </div>

          <div className="topbar__actions">
            <EscritorioSelector />
            <button className="icon-button" type="button" aria-label="Próximos compromissos" onClick={() => navigate('/agenda')}>
              <Bell size={18} />
            </button>
            <button className="profile-chip" type="button" aria-label="Abrir configurações" onClick={() => navigate('/configuracoes')}>
              <span className="profile-chip__avatar">{initials}</span>
              <span className="profile-chip__copy">
                <strong>{displayName}</strong>
                <small>{user?.email || 'Administrador'}</small>
              </span>
            </button>
          </div>
        </header>

        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
