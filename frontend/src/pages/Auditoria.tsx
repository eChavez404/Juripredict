import { useCallback, useEffect, useState } from 'react';
import { ClipboardList, RefreshCw } from 'lucide-react';
import ProtectedContent from '../components/auth/ProtectedContent';
import SettingsNav from '../components/settings/SettingsNav';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import ViewToggle from '../components/ui/ViewToggle';
import { auditoriaService } from '../features/auditoria/api';
import type { EventoAuditoria } from '../features/auditoria/types';
import { CAPABILITIES } from '../features/escritorios/types';
import useViewPreference from '../hooks/useViewPreference';
import { getApiError } from '../services/api';

const formatDateTime = (value: string) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? 'Data não informada'
    : new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(date);
};

const AuditoriaContent = () => {
  const [eventos, setEventos] = useState<EventoAuditoria[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [view, setView] = useViewPreference('juripredict:auditoria-view');

  const loadEventos = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setEventos(await auditoriaService.list());
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadEventos(); }, [loadEventos]);

  if (loading) return <div className="panel empty-state" role="status">Carregando trilha de auditoria...</div>;

  return (
    <>
      {error && <Feedback type="error">{error}</Feedback>}
      {!error && eventos.length === 0 && (
        <div className="panel empty-state audit-empty">
          <ClipboardList size={25} aria-hidden="true" />
          <strong>Nenhum evento registrado</strong>
          <span>As ações relevantes do escritório serão apresentadas aqui.</span>
        </div>
      )}
      {eventos.length > 0 && (
        <section className={`panel${view === 'table' ? ' table-panel' : ''}`} aria-label="Trilha de auditoria">
          <div className="section-heading team-heading">
            <div><h2>Atividades recentes</h2><p>Registro somente para consulta</p></div>
            <div className="section-heading__actions">
              <ViewToggle value={view} onChange={setView} label="Visualização da auditoria" />
              <button className="button button--secondary button--small" type="button" onClick={() => void loadEventos()}>
                <RefreshCw size={14} aria-hidden="true" /> Atualizar
              </button>
            </div>
          </div>
          {view === 'table' ? (
            <div className="table-scroll">
              <table className="data-table audit-table">
                <caption className="sr-only">Eventos registrados no escritório ativo</caption>
                <thead><tr><th>Data e hora</th><th>Ator</th><th>Ação</th><th>Recurso</th><th>Descrição</th></tr></thead>
                <tbody>
                  {eventos.map((evento) => (
                    <tr key={evento.id}>
                      <td><time dateTime={evento.ocorridoEm}>{formatDateTime(evento.ocorridoEm)}</time></td>
                      <td>{evento.atorNome}</td>
                      <td><span className="status-badge status-badge--cyan">{evento.acao}</span></td>
                      <td>{evento.recurso}</td>
                      <td><span className="table-secondary">{evento.descricao}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="collection-grid collection-grid--inside-panel" aria-label="Eventos de auditoria em cards">
              {eventos.map((evento) => (
                <article className="collection-card collection-card--nested" key={evento.id}>
                  <header className="collection-card__header">
                    <span className="collection-card__icon"><ClipboardList size={20} aria-hidden="true" /></span>
                    <div className="collection-card__identity">
                      <span className="collection-card__eyebrow">Evento de auditoria</span>
                      <h2>{evento.acao}</h2>
                      <p><time dateTime={evento.ocorridoEm}>{formatDateTime(evento.ocorridoEm)}</time></p>
                    </div>
                    <span className="status-badge status-badge--cyan">{evento.recurso}</span>
                  </header>
                  <dl className="collection-card__details">
                    <div><dt>Ator</dt><dd>{evento.atorNome}</dd></div>
                    <div><dt>Recurso</dt><dd>{evento.recurso}</dd></div>
                    <div className="collection-card__field--full"><dt>Descrição</dt><dd>{evento.descricao}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </>
  );
};

const Auditoria = () => (
  <div className="page">
    <PageHeader
      eyebrow="Configurações"
      title="Auditoria"
      description="Acompanhe ações relevantes realizadas no escritório."
      backTo="/configuracoes"
      backLabel="Voltar para configurações"
    />
    <SettingsNav />
    <ProtectedContent capability={CAPABILITIES.auditoriaVisualizar}>
      <AuditoriaContent />
    </ProtectedContent>
  </div>
);

export default Auditoria;
