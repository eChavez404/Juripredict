import { useState } from 'react';
import { Building2 } from 'lucide-react';
import { useAuth } from '../../contexts/auth';
import { getApiError } from '../../services/api';

const EscritorioSelector = () => {
  const { activeEscritorio, memberships, selectEscritorio } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const escritoriosAtivos = memberships.filter((membership) => membership.status === 'ATIVO');

  if (escritoriosAtivos.length === 0) return null;

  const handleChange = async (value: string) => {
    setBusy(true);
    setError('');
    try {
      await selectEscritorio(value);
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="office-selector">
      <Building2 size={16} aria-hidden="true" />
      <label className="sr-only" htmlFor="active-office">Escritório ativo</label>
      <select
        id="active-office"
        value={activeEscritorio?.id ?? ''}
        disabled={busy || escritoriosAtivos.length === 1}
        aria-describedby={error ? 'office-selector-error' : undefined}
        onChange={(event) => void handleChange(event.target.value)}
      >
        {!activeEscritorio && <option value="" disabled>Selecione um escritório</option>}
        {escritoriosAtivos.map(({ escritorio }) => (
          <option value={escritorio.id} key={escritorio.id}>{escritorio.nome}</option>
        ))}
      </select>
      {busy && <span className="sr-only" role="status">Alterando escritório...</span>}
      {error && <span className="office-selector__error" id="office-selector-error" role="alert">{error}</span>}
    </div>
  );
};

export default EscritorioSelector;
