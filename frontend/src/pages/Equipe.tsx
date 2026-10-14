import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, ShieldCheck, UserCheck, UserX, Users } from 'lucide-react';
import ProtectedContent from '../components/auth/ProtectedContent';
import PermissionGate from '../components/auth/PermissionGate';
import SettingsNav from '../components/settings/SettingsNav';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import ViewToggle from '../components/ui/ViewToggle';
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
import useViewPreference from '../hooks/useViewPreference';

const EquipeContent = () => {
  const { activeEscritorio } = useAuth();
  const [membros, setMembros] = useState<MembroResumo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [view, setView] = useViewPreference('juripredict:equipe-view');

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

  const renderRoleControl = (membro: MembroResumo, busy: boolean, prefix: string) => (
    <PermissionGate
      capability={CAPABILITIES.membrosGerenciar}
      fallback={<span>{papelLabels[membro.papel] ?? membro.papel}</span>}
    >
      <label className="sr-only" htmlFor={`${prefix}-${membro.id}`}>Papel de {membro.usuario.nome || membro.usuario.email}</label>
      <select
        className="table-select"
        id={`${prefix}-${membro.id}`}
        value={membro.papel}
        disabled={busy}
        onChange={(event) => void updateMembro(membro, { papel: event.target.value as PapelMembro })}
      >
        {papeisDisponiveis.map((papel) => <option value={papel} key={papel}>{papelLabels[papel]}</option>)}
      </select>
    </PermissionGate>
  );

  const renderStatusAction = (membro: MembroResumo, busy: boolean, isActive: boolean) => (
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
  );

  if (loading) return <div className="panel empty-state" role="status">Carregando equipe...</div>;

  return (
    <>
      {error && <Feedback type="error">{error}</Feedback>}
      <section className={`panel${view === 'table' ? ' table-panel' : ''}`} aria-labelledby="team-list-title">
        <div className="section-heading team-heading">
          <div>
            <h2 id="team-list-title"><Users size={18} aria-hidden="true" /> Pessoas com acesso</h2>
            <p>{activeEscritorio?.nome ?? 'Escritório ativo'} · {membros.length} {membros.length === 1 ? 'membro' : 'membros'}</p>
          </div>
          <div className="section-heading__actions">
            <ViewToggle value={view} onChange={setView} label="Visualização da equipe" />
            <button className="button button--secondary button--small" type="button" onClick={() => void loadMembros()}>
              <RefreshCw size={14} aria-hidden="true" /> Atualizar
            </button>
          </div>
        </div>

        {view === 'table' ? (
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
                      <td>{renderRoleControl(membro, busy, 'member-role')}</td>
                      <td>
                        <span className={`status-badge status-badge--${isActive ? 'green' : 'gray'}`}>
                          {statusMembroLabels[membro.status] ?? membro.status}
                        </span>
                      </td>
                      <td>{renderStatusAction(membro, busy, isActive)}</td>
                    </tr>
                  );
                })}
                {membros.length === 0 && (
                  <tr><td colSpan={4} className="empty-state">Nenhum membro encontrado neste escritório.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        ) : membros.length === 0 ? (
          <div className="empty-state">Nenhum membro encontrado neste escritório.</div>
        ) : (
          <div className="collection-grid collection-grid--inside-panel" aria-label="Membros da equipe em cards">
            {membros.map((membro) => {
              const busy = busyId === membro.id;
              const isActive = membro.status === 'ATIVO';
              return (
                <article className="collection-card collection-card--nested" key={membro.id}>
                  <header className="collection-card__header">
                    <span className="collection-card__icon"><Users size={20} aria-hidden="true" /></span>
                    <div className="collection-card__identity">
                      <span className="collection-card__eyebrow">Membro da equipe</span>
                      <h2>{membro.usuario.nome || membro.usuario.username}</h2>
                      <p>{membro.usuario.email}</p>
                    </div>
                    <span className={`status-badge status-badge--${isActive ? 'green' : 'gray'}`}>
                      {statusMembroLabels[membro.status] ?? membro.status}
                    </span>
                  </header>
                  <dl className="collection-card__details">
                    <div className="collection-card__field--full"><dt>Papel no escritório</dt><dd>{renderRoleControl(membro, busy, 'member-card-role')}</dd></div>
                  </dl>
                  <footer className="collection-card__footer">
                    <span>Acesso ao escritório</span>
                    {renderStatusAction(membro, busy, isActive)}
                  </footer>
                </article>
              );
            })}
          </div>
        )}
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
      backTo="/configuracoes"
      backLabel="Voltar para configurações"
      action={<span className="status-badge status-badge--cyan"><ShieldCheck size={13} aria-hidden="true" /> Acesso controlado</span>}
    />
    <SettingsNav />
    <ProtectedContent anyOf={[CAPABILITIES.membrosVisualizar, CAPABILITIES.membrosGerenciar]}>
      <EquipeContent />
    </ProtectedContent>
  </div>
);

export default Equipe;
