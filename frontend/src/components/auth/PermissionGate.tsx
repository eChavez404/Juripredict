import type { ReactNode } from 'react';
import { useAuth } from '../../contexts/auth';
import type { Capability } from '../../features/escritorios/types';

type PermissionGateProps = {
  capability?: Capability;
  anyOf?: Capability[];
  allOf?: Capability[];
  fallback?: ReactNode;
  children: ReactNode;
};

const PermissionGate = ({
  capability,
  anyOf = [],
  allOf = [],
  fallback = null,
  children,
}: PermissionGateProps) => {
  const { hasCapability } = useAuth();
  const requiredAny = capability ? [...anyOf, capability] : anyOf;
  const hasAny = requiredAny.length === 0 || requiredAny.some(hasCapability);
  const hasAll = allOf.every(hasCapability);

  return hasAny && hasAll ? <>{children}</> : <>{fallback}</>;
};

export default PermissionGate;
