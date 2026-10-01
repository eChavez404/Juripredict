import { NavLink } from 'react-router-dom';
import PermissionGate from '../auth/PermissionGate';
import { CAPABILITIES } from '../../features/escritorios/types';

const SettingsNav = () => (
  <nav className="settings-nav" aria-label="Configurações">
    <NavLink end to="/configuracoes">Perfil e segurança</NavLink>
    <PermissionGate anyOf={[CAPABILITIES.membrosVisualizar, CAPABILITIES.membrosGerenciar]}>
      <NavLink to="/configuracoes/equipe">Equipe</NavLink>
    </PermissionGate>
    <PermissionGate capability={CAPABILITIES.auditoriaVisualizar}>
      <NavLink to="/configuracoes/auditoria">Auditoria</NavLink>
    </PermissionGate>
  </nav>
);

export default SettingsNav;
