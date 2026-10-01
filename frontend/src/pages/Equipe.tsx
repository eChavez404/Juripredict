import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, ShieldCheck, UserCheck, UserX, Users } from 'lucide-react';
import ProtectedContent from '../components/auth/ProtectedContent';
import PermissionGate from '../components/auth/PermissionGate';
import SettingsNav from '../components/settings/SettingsNav';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import { useAuth } from '../contexts/auth';
import { equipeService } from '../features/escritorios/api';
import {
  CAPABILITIES,
  papeisDisponiveis,
  papelLabels,
  statusMembroLabels,
  type MembroResumo,
  type PapelMembro,
  type StatusMembro,
} from '../features/escritorios/types';
import { getApiError } from '../services/api';

const EquipeContent = () => {
  const { activeEscritorio } = useAuth();
  const [membros, setMembros] = useState<MembroResumo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const loadMembros = useCallback(async () => {
    if (!activeEscritorio) {
      setMembros([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError('');
    try {
      setMembros(await equipeService.list(activeEscritorio.id));
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, [activeEscritorio]);

  useEffect(() => { void loadMembros(); }, [loadMembros]);

  const updateMembro = async (
    membro: MembroResumo,
    payload: Partial<{ papel: PapelMembro; status: StatusMembro }>,
  ) => {
    if (!activeEscritorio) return;
    setBusyId(membro.id);
    setError('');
    try {
      await equipeService.update(activeEscritorio.id, membro.id, payload);
      await loadMembros();
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusyId(null);
    }
  };

  if (loading) return <div className="panel empty-state" role="status">Carregando equipe...</div>;

  return (
    <>
      {error && <Feedback type="error">{error}</Feedback>}
      <section className="panel table-panel" aria-labelledby="team-list-title">
        <div className="section-heading team-heading">
          <div>
            <h2 id="team-list-title"><Users size={18} aria-hidden="true" /> Pessoas com acesso</h2>
            <p>{activeEscritorio?.nome ?? 'Escritório ativo'} · {membros.length} {membros.length === 1 ? 'membro' : 'membros'}</p>
          </div>
          <button className="button button--secondary button--small" type="button" onClick={() => void loadMembros()}>
            <RefreshCw size={14} aria-hidden="true" /> Atualizar
          </button>
        </div>

        <div className="table-scroll">
          <table className="data-table team-table">
            <caption className="sr-only">Membros e permissões do escritório ativo</caption>
            <thead>
              <tr><th>Pessoa</th><th>Papel</th><th>Status</th><th>Ações</th></tr>
            </thead>
            <tbody>
              {membros.map((membro) => {
                const busy = busyId === membro.id;
                const isActive = membro.status === 'ATIVO';
                return (
                  <tr key={membro.id}>
                    <td>
                      <strong className="team-member__name">{membro.usuario.nome || membro.usuario.username}</strong>
                      <span className="table-secondary">{membro.usuario.email}</span>
                    </td>
                    <td>
                      <PermissionGate
                        capability={CAPABILITIES.membrosGerenciar}
                        fallback={<span>{papelLabels[membro.papel] ?? membro.papel}</span>}
                      >
                        <label className="sr-only" htmlFor={`member-role-${membro.id}`}>Papel de {membro.usuario.nome || membro.usuario.email}</label>
                        <select
                          className="table-select"
                          id={`member-role-${membro.id}`}
                          value={membro.papel}
                          disabled={busy}
                          onChange={(event) => void updateMembro(membro, { papel: event.target.value as PapelMembro })}
                        >
                          {papeisDisponiveis.map((papel) => <option value={papel} key={papel}>{papelLabels[papel]}</option>)}
                        </select>
                      </PermissionGate>
                    </td>
                    <td>
                      <span className={`status-badge status-badge--${isActive ? 'green' : 'gray'}`}>
                        {statusMembroLabels[membro.status] ?? membro.status}
                      </span>
                    </td>
                    <td>
                      <PermissionGate
                        capability={CAPABILITIES.membrosGerenciar}
                        fallback={<span className="table-secondary">Somente leitura</span>}
                      >
                        <button
                          className={`button button--small ${isActive ? 'button--secondary' : 'button--primary'}`}
                          type="button"
                          disabled={busy}
                          onClick={() => void updateMembro(membro, { status: isActive ? 'SUSPENSO' : 'ATIVO' })}
                        >
                          {isActive ? <UserX size={14} aria-hidden="true" /> : <UserCheck size={14} aria-hidden="true" />}
                          {busy ? 'Salvando...' : isActive ? 'Suspender' : 'Reativar'}
                        </button>
                      </PermissionGate>
                    </td>
                  </tr>
                );
              })}
              {membros.length === 0 && (
                <tr><td colSpan={4} className="empty-state">Nenhum membro encontrado neste escritório.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
};

const Equipe = () => (
  <div className="page">
    <PageHeader
      eyebrow="Configurações"
      title="Equipe"
      description="Consulte os acessos e administre os papéis do escritório ativo."
      action={<span className="status-badge status-badge--cyan"><ShieldCheck size={13} aria-hidden="true" /> Acesso controlado</span>}
    />
    <SettingsNav />
    <ProtectedContent anyOf={[CAPABILITIES.membrosVisualizar, CAPABILITIES.membrosGerenciar]}>
      <EquipeContent />
    </ProtectedContent>
  </div>
);

export default Equipe;
