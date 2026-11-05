import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { MailPlus, Send } from 'lucide-react';
import ConfirmDialog from '../ui/ConfirmDialog';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';
import { conviteService } from '../../features/escritorios/api';
import {
  papeisConvidaveis,
  papelLabels,
  type Convite,
  type PapelMembro,
} from '../../features/escritorios/types';
import { getApiError } from '../../services/api';

const formatarData = (iso: string) => new Date(iso).toLocaleDateString('pt-BR');

/** Convites pendentes do escritório: listar, enviar e revogar. */
const ConvitesPanel = ({ escritorioId }: { escritorioId: string }) => {
  const [convites, setConvites] = useState<Convite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [aviso, setAviso] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [papel, setPapel] = useState<PapelMembro>('ADVOGADO');
  const [revogando, setRevogando] = useState<Convite | null>(null);
  const [busy, setBusy] = useState(false);

  const carregar = useCallback(async () => {
    setError('');
    try {
      setConvites(await conviteService.list(escritorioId));
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, [escritorioId]);

  useEffect(() => { void carregar(); }, [carregar]);

  const enviar = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await conviteService.create(escritorioId, { email, papel });
      setAviso(`Convite enviado para ${email}.`);
      setModalOpen(false);
      setEmail('');
      await carregar();
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  const revogar = async () => {
    if (!revogando) return;
    setBusy(true);
    setError('');
    try {
      await conviteService.revoke(escritorioId, revogando.id);
      setRevogando(null);
      await carregar();
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel" aria-labelledby="invites-title">
      <div className="section-heading team-heading">
        <div>
          <h2 id="invites-title"><MailPlus size={18} aria-hidden="true" /> Convites pendentes</h2>
          <p>Quem recebe o convite define a própria senha e entra com o papel escolhido.</p>
        </div>
        <button className="button button--primary button--small" type="button" onClick={() => setModalOpen(true)}>
          <Send size={14} aria-hidden="true" /> Convidar pessoa
        </button>
      </div>

      {error && <Feedback type="error">{error}</Feedback>}
      {aviso && <Feedback type="success">{aviso}</Feedback>}

      {loading ? (
        <div className="empty-state" role="status">Carregando convites...</div>
      ) : convites.length === 0 ? (
        <div className="empty-state">Nenhum convite pendente.</div>
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <caption className="sr-only">Convites aguardando aceite</caption>
            <thead>
              <tr><th>E-mail</th><th>Papel</th><th>Expira em</th><th>Ações</th></tr>
            </thead>
            <tbody>
              {convites.map((convite) => (
                <tr key={convite.id}>
                  <td>{convite.email}</td>
                  <td>{papelLabels[convite.papel] ?? convite.papel}</td>
                  <td>{formatarData(convite.expira_em)}</td>
                  <td>
                    <button
                      className="button button--secondary button--small"
                      type="button"
                      onClick={() => setRevogando(convite)}
                    >
                      Revogar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={modalOpen}
        title="Convidar pessoa"
        description="Enviaremos um link por e-mail. Ele vale por 7 dias e só pode ser usado uma vez."
        onClose={() => !busy && setModalOpen(false)}
      >
        <form onSubmit={enviar}>
          <div className="form-grid">
            <label className="form-field form-field--full">
              E-mail
              <input
                className="input"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>
            <label className="form-field form-field--full">
              Papel
              <select value={papel} onChange={(event) => setPapel(event.target.value as PapelMembro)}>
                {papeisConvidaveis.map((item) => (
                  <option value={item} key={item}>{papelLabels[item]}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="form-actions">
            <button className="button button--secondary" type="button" onClick={() => setModalOpen(false)} disabled={busy}>
              Cancelar
            </button>
            <button className="button button--primary" type="submit" disabled={busy}>
              {busy ? 'Enviando...' : 'Enviar convite'}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(revogando)}
        title="Revogar convite"
        message={`O link enviado para ${revogando?.email ?? 'esta pessoa'} deixará de funcionar.`}
        confirmLabel="Revogar"
        busyLabel="Revogando..."
        busy={busy}
        onCancel={() => setRevogando(null)}
        onConfirm={revogar}
      />
    </section>
  );
};

export default ConvitesPanel;
