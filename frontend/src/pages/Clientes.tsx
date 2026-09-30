import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { Building2, Mail, Pencil, Phone, Plus, Trash2, User } from 'lucide-react';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import Feedback from '../components/ui/Feedback';
import Modal from '../components/ui/Modal';
import PageHeader from '../components/ui/PageHeader';
import SearchField from '../components/ui/SearchField';
import { getApiError } from '../services/api';
import { clienteService } from '../services/juripredict';
import type { Cliente, ClientePayload } from '../types';

const emptyForm: ClientePayload = {
  nome: '',
  cpf_cnpj: '',
  tipo: 'PF',
  email: '',
  telefone: '',
};

const maskDocument = (document: string) => {
  const digits = document.replace(/\D/g, '');
  if (digits.length === 11) return `***.***.${digits.slice(6, 9)}-${digits.slice(9)}`;
  if (digits.length === 14) return `**.***.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12)}`;
  return document;
};

const Clientes = () => {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [busca, setBusca] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Cliente | null>(null);
  const [deleting, setDeleting] = useState<Cliente | null>(null);
  const [form, setForm] = useState<ClientePayload>(emptyForm);

  const loadClientes = useCallback(async () => {
    try {
      const data = await clienteService.list();
      setClientes(data);
      setError('');
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadClientes(); }, [loadClientes]);

  const filtrados = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase('pt-BR');
    return clientes.filter((cliente) => (
      cliente.nome.toLocaleLowerCase('pt-BR').includes(termo)
      || (cliente.email ?? '').toLocaleLowerCase('pt-BR').includes(termo)
    ));
  }, [busca, clientes]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setFormError('');
    setModalOpen(true);
  };

  const openEdit = (cliente: Cliente) => {
    setEditing(cliente);
    setForm({
      nome: cliente.nome,
      cpf_cnpj: cliente.cpf_cnpj,
      tipo: cliente.tipo,
      email: cliente.email ?? '',
      telefone: cliente.telefone ?? '',
    });
    setFormError('');
    setModalOpen(true);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFormError('');
    try {
      if (editing) await clienteService.update(editing.id, form);
      else await clienteService.create(form);
      setModalOpen(false);
      await loadClientes();
    } catch (requestError) {
      setFormError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    setError('');
    try {
      await clienteService.remove(deleting.id);
      setDeleting(null);
      await loadClientes();
    } catch (requestError) {
      setError(getApiError(requestError));
      setDeleting(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Relacionamento"
        title="Clientes"
        description="Cadastre os contatos e acompanhe a carteira de cada cliente."
        action={(
          <button className="button button--primary" type="button" onClick={openCreate}>
            <Plus size={17} /> Novo cliente
          </button>
        )}
      />

      {error && <Feedback type="error">{error}</Feedback>}

      <SearchField value={busca} onChange={setBusca} placeholder="Buscar por nome ou e-mail..." label="Buscar clientes" />

      {loading ? (
        <div className="panel empty-state">Carregando clientes...</div>
      ) : (
        <section className="grid clients-grid" aria-label="Lista de clientes">
          {filtrados.map((cliente) => {
            const isCompany = cliente.tipo === 'PJ';
            const AvatarIcon = isCompany ? Building2 : User;
            return (
              <article className="panel client-card" key={cliente.id}>
                <div className="client-card__header">
                  <span className={`client-card__avatar${isCompany ? ' client-card__avatar--company' : ''}`}>
                    <AvatarIcon size={21} aria-hidden="true" />
                  </span>
                  <div className="client-card__identity">
                    <h2>{cliente.nome}</h2>
                    <span className={`status-badge status-badge--${isCompany ? 'yellow' : 'cyan'}`}>
                      {isCompany ? 'Pessoa jurídica' : 'Pessoa física'}
                    </span>
                  </div>
                  <div className="card-actions">
                    <button className="action-button" type="button" aria-label={`Editar ${cliente.nome}`} onClick={() => openEdit(cliente)}><Pencil size={15} /></button>
                    <button className="action-button action-button--danger" type="button" aria-label={`Excluir ${cliente.nome}`} onClick={() => setDeleting(cliente)}><Trash2 size={15} /></button>
                  </div>
                </div>

                <div className="client-card__details">
                  <span><Mail size={14} aria-hidden="true" /> {cliente.email || 'E-mail não informado'}</span>
                  <span><Phone size={14} aria-hidden="true" /> {cliente.telefone || 'Telefone não informado'}</span>
                </div>

                <footer className="client-card__footer">
                  <span>CPF/CNPJ: {maskDocument(cliente.cpf_cnpj)}</span>
                  <strong>{cliente.processos_count} {cliente.processos_count === 1 ? 'processo' : 'processos'}</strong>
                </footer>
              </article>
            );
          })}
          {filtrados.length === 0 && <div className="panel empty-state">Nenhum cliente encontrado.</div>}
        </section>
      )}

      <Modal open={modalOpen} title={editing ? 'Editar cliente' : 'Novo cliente'} description="Os dados de CPF/CNPJ são armazenados de forma criptografada." onClose={() => !busy && setModalOpen(false)}>
        <form className="entity-form" onSubmit={handleSubmit}>
          {formError && <Feedback type="error">{formError}</Feedback>}
          <div className="form-grid">
            <label className="form-field form-field--full">
              <span>Nome completo ou razão social</span>
              <input value={form.nome} onChange={(event) => setForm({ ...form, nome: event.target.value })} required />
            </label>
            <label className="form-field">
              <span>Tipo</span>
              <select value={form.tipo} onChange={(event) => setForm({ ...form, tipo: event.target.value as 'PF' | 'PJ' })}>
                <option value="PF">Pessoa física</option>
                <option value="PJ">Pessoa jurídica</option>
              </select>
            </label>
            <label className="form-field">
              <span>CPF/CNPJ</span>
              <input value={form.cpf_cnpj} onChange={(event) => setForm({ ...form, cpf_cnpj: event.target.value })} maxLength={20} required />
            </label>
            <label className="form-field">
              <span>E-mail</span>
              <input type="email" value={form.email ?? ''} onChange={(event) => setForm({ ...form, email: event.target.value })} />
            </label>
            <label className="form-field">
              <span>Telefone</span>
              <input value={form.telefone ?? ''} onChange={(event) => setForm({ ...form, telefone: event.target.value })} maxLength={20} />
            </label>
          </div>
          <div className="form-actions">
            <button className="button button--secondary" type="button" onClick={() => setModalOpen(false)} disabled={busy}>Cancelar</button>
            <button className="button button--primary" type="submit" disabled={busy}>{busy ? 'Salvando...' : 'Salvar cliente'}</button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        title="Excluir cliente"
        message={`Deseja realmente excluir ${deleting?.nome ?? 'este cliente'}? Clientes com processos vinculados são protegidos.`}
        busy={busy}
        onCancel={() => setDeleting(null)}
        onConfirm={handleDelete}
      />
    </div>
  );
};

export default Clientes;
