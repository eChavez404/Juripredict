import { useCallback, useEffect, useState } from 'react';
import { ClipboardList, RefreshCw } from 'lucide-react';
import ProtectedContent from '../components/auth/ProtectedContent';
import SettingsNav from '../components/settings/SettingsNav';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import { auditoriaService } from '../features/auditoria/api';
import type { EventoAuditoria } from '../features/auditoria/types';
import { CAPABILITIES } from '../features/escritorios/types';
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
        <section className="panel table-panel" aria-label="Trilha de auditoria">
          <div className="section-heading team-heading">
            <div><h2>Atividades recentes</h2><p>Registro somente para consulta</p></div>
            <button className="button button--secondary button--small" type="button" onClick={() => void loadEventos()}>
              <RefreshCw size={14} aria-hidden="true" /> Atualizar
            </button>
          </div>
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
    />
    <SettingsNav />
    <ProtectedContent capability={CAPABILITIES.auditoriaVisualizar}>
      <AuditoriaContent />
    </ProtectedContent>
  </div>
);

export default Auditoria;
