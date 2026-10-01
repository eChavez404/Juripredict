import type { ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import PermissionGate from './PermissionGate';
import type { Capability } from '../../features/escritorios/types';

type ProtectedContentProps = {
  anyOf?: Capability[];
  capability?: Capability;
  children: ReactNode;
};

const denied = (
  <div className="panel empty-state access-denied" role="alert">
    <ShieldAlert size={24} aria-hidden="true" />
    <strong>Acesso restrito</strong>
    <span>Você não possui permissão para visualizar esta área.</span>
  </div>
);

const ProtectedContent = ({ anyOf, capability, children }: ProtectedContentProps) => (
  <PermissionGate capability={capability} anyOf={anyOf} fallback={denied}>
    {children}
  </PermissionGate>
);

export default ProtectedContent;
