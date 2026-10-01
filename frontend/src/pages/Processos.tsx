import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import { FileText, Filter, Link as LinkIcon, Pencil, Plus, Trash2 } from 'lucide-react';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import Feedback from '../components/ui/Feedback';
import Modal from '../components/ui/Modal';
import PageHeader from '../components/ui/PageHeader';
import SearchField from '../components/ui/SearchField';
import { getApiError } from '../services/api';
import { clienteService, processoService } from '../services/juripredict';
import type { Cliente, Processo, ProcessoArea, ProcessoResultado, ProcessoStatus } from '../types';

type ProcessoForm = {
  numero_cnj: string;
  titulo: string;
  area: ProcessoArea;
  vara: string;
  comarca: string;
  cliente: string;
  parte_contraria: string;
  status: ProcessoStatus;
  resultado: ProcessoResultado;
  valor_causa: string;
  data_distribuicao: string;
  observacoes: string;
  arquivo: File | null;
};

const emptyForm: ProcessoForm = {
  numero_cnj: '',
  titulo: '',
  area: 'TRABALHISTA',
  vara: '',
  comarca: '',
  cliente: '',
  parte_contraria: '',
  status: 'ATIVO',
  resultado: 'PENDENTE',
  valor_causa: '',
  data_distribuicao: '',
  observacoes: '',
  arquivo: null,
};

const statusTone: Record<ProcessoStatus, string> = {
  ATIVO: 'green',
  SUSPENSO: 'yellow',
  ARQUIVADO: 'gray',
};

const statusOptions: Array<'TODOS' | ProcessoStatus> = ['TODOS', 'ATIVO', 'SUSPENSO', 'ARQUIVADO'];

const formatDate = (value: string) => new Intl.DateTimeFormat('pt-BR').format(new Date(value));

const Processos = () => {
  const [processos, setProcessos] = useState<Processo[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [busca, setBusca] = useState('');
  const [filtroStatus, setFiltroStatus] = useState<'TODOS' | ProcessoStatus>('TODOS');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Processo | null>(null);
  const [deleting, setDeleting] = useState<Processo | null>(null);
  const [form, setForm] = useState<ProcessoForm>(emptyForm);

  const loadData = useCallback(async () => {
    try {
      const [processData, clientData] = await Promise.all([processoService.list(), clienteService.list()]);
      setProcessos(processData);
      setClientes(clientData);
      setError('');
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadData(); }, [loadData]);

  const filtrados = useMemo(() => {
    const termo = busca.trim().toLocaleLowerCase('pt-BR');
    return processos.filter((processo) => {
      const correspondeABusca = processo.numero_cnj.toLocaleLowerCase('pt-BR').includes(termo)
        || processo.cliente_nome.toLocaleLowerCase('pt-BR').includes(termo)
        || processo.parte_contraria.toLocaleLowerCase('pt-BR').includes(termo);
      return correspondeABusca && (filtroStatus === 'TODOS' || processo.status === filtroStatus);
    });
  }, [busca, filtroStatus, processos]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...emptyForm, cliente: clientes[0]?.id.toString() ?? '' });
    setFormError('');
    setModalOpen(true);
  };

  const openEdit = (processo: Processo) => {
    setEditing(processo);
    setForm({
      numero_cnj: processo.numero_cnj,
      titulo: processo.titulo,
      area: processo.area,
      vara: processo.vara,
      comarca: processo.comarca,
      cliente: processo.cliente.toString(),
      parte_contraria: processo.parte_contraria,
      status: processo.status,
      resultado: processo.resultado,
      valor_causa: processo.valor_causa ?? '',
      data_distribuicao: processo.data_distribuicao ?? '',
      observacoes: processo.observacoes,
      arquivo: null,
    });
    setFormError('');
    setModalOpen(true);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFormError('');
    const payload = new FormData();
    Object.entries(form).forEach(([key, value]) => {
      if (key === 'arquivo') {
        if (value instanceof File) payload.append('arquivo_peticao_inicial', value);
      } else {
        payload.append(key, String(value));
      }
    });

    try {
      await processoService.save(payload, editing?.id);
      setModalOpen(false);
      await loadData();
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
      await processoService.remove(deleting.id);
      setDeleting(null);
      await loadData();
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
        eyebrow="Operação jurídica"
        title="Processos"
        description="Cadastre casos, acompanhe status, resultados e documentos."
        action={(
          <button className="button button--primary" type="button" onClick={openCreate} disabled={clientes.length === 0}>
            <Plus size={17} /> Novo processo
          </button>
        )}
      />

      {error && <Feedback type="error">{error}</Feedback>}
      {!loading && clientes.length === 0 && <Feedback>Cadastre pelo menos um cliente antes de criar um processo.</Feedback>}

      <section className="panel toolbar" aria-label="Filtros dos processos">
        <SearchField value={busca} onChange={setBusca} placeholder="Buscar por CNJ, cliente ou parte contrária..." label="Buscar processos" />
        <div className="filter-group">
          <span className="filter-group__label"><Filter size={14} /> Status</span>
          {statusOptions.map((item) => (
            <button key={item} className={`filter-chip${filtroStatus === item ? ' filter-chip--active' : ''}`} type="button" onClick={() => setFiltroStatus(item)}>
              {item === 'TODOS' ? 'Todos' : item.charAt(0) + item.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </section>

      <section className="panel table-panel" aria-label="Lista de processos">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr><th>Nº CNJ</th><th>Cliente</th><th>Vara / comarca</th><th>Parte contrária</th><th>Status</th><th>Cadastro</th><th>Ações</th></tr>
            </thead>
            <tbody>
              {loading && <tr><td colSpan={7} className="empty-state">Carregando processos...</td></tr>}
              {!loading && filtrados.map((processo) => (
                <tr key={processo.id}>
                  <td>
                    <span className="table-primary"><FileText size={15} /> {processo.numero_cnj}</span>
                    {processo.titulo && <span className="table-secondary">{processo.titulo}</span>}
                  </td>
                  <td>{processo.cliente_nome}</td>
                  <td><span className="table-secondary">{processo.vara}<br />{processo.comarca}</span></td>
                  <td>{processo.parte_contraria}</td>
                  <td><span className={`status-badge status-badge--${statusTone[processo.status]}`}>{processo.status}</span></td>
                  <td><span className="table-secondary">{formatDate(processo.criado_em)}</span></td>
                  <td>
                    <div className="table-actions">
                      {processo.arquivo_peticao_inicial_url && (
                        <a className="action-button" href={processo.arquivo_peticao_inicial_url} target="_blank" rel="noreferrer" aria-label="Abrir documento"><LinkIcon size={15} /></a>
                      )}
                      <button className="action-button" type="button" aria-label="Editar processo" onClick={() => openEdit(processo)}><Pencil size={15} /></button>
                      <button className="action-button action-button--danger" type="button" aria-label="Excluir processo" onClick={() => setDeleting(processo)}><Trash2 size={15} /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && filtrados.length === 0 && <tr><td colSpan={7} className="empty-state">Nenhum processo encontrado.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <Modal open={modalOpen} title={editing ? 'Editar processo' : 'Novo processo'} description="Preencha as informações principais do caso." size="large" onClose={() => !busy && setModalOpen(false)}>
        <form className="entity-form" onSubmit={handleSubmit}>
          {formError && <Feedback type="error">{formError}</Feedback>}
          <div className="form-grid">
            <label className="form-field"><span>Número CNJ</span><input value={form.numero_cnj} onChange={(event) => setForm({ ...form, numero_cnj: event.target.value })} placeholder="0000000-00.0000.0.00.0000" required /></label>
            <label className="form-field"><span>Cliente</span><select value={form.cliente} onChange={(event) => setForm({ ...form, cliente: event.target.value })} required><option value="">Selecione</option>{clientes.map((cliente) => <option value={cliente.id} key={cliente.id}>{cliente.nome}</option>)}</select></label>
            <label className="form-field form-field--full"><span>Título ou objeto</span><input value={form.titulo} onChange={(event) => setForm({ ...form, titulo: event.target.value })} placeholder="Ex.: Reclamação trabalhista" /></label>
            <label className="form-field"><span>Área</span><select value={form.area} onChange={(event) => setForm({ ...form, area: event.target.value as ProcessoArea })}><option value="TRABALHISTA">Trabalhista</option><option value="CIVEL">Cível</option><option value="PREVIDENCIARIO">Previdenciário</option><option value="TRIBUTARIO">Tributário</option><option value="CRIMINAL">Criminal</option><option value="OUTRO">Outro</option></select></label>
            <label className="form-field"><span>Parte contrária</span><input value={form.parte_contraria} onChange={(event) => setForm({ ...form, parte_contraria: event.target.value })} required /></label>
            <label className="form-field"><span>Vara</span><input value={form.vara} onChange={(event) => setForm({ ...form, vara: event.target.value })} required /></label>
            <label className="form-field"><span>Comarca</span><input value={form.comarca} onChange={(event) => setForm({ ...form, comarca: event.target.value })} required /></label>
            <label className="form-field"><span>Status</span><select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as ProcessoStatus })}><option value="ATIVO">Ativo</option><option value="SUSPENSO">Suspenso</option><option value="ARQUIVADO">Arquivado</option></select></label>
            <label className="form-field"><span>Resultado</span><select value={form.resultado} onChange={(event) => setForm({ ...form, resultado: event.target.value as ProcessoResultado })}><option value="PENDENTE">Pendente</option><option value="FAVORAVEL">Favorável</option><option value="DESFAVORAVEL">Desfavorável</option><option value="ACORDO">Acordo</option></select></label>
            <label className="form-field"><span>Valor da causa</span><input type="number" min="0" step="0.01" value={form.valor_causa} onChange={(event) => setForm({ ...form, valor_causa: event.target.value })} /></label>
            <label className="form-field"><span>Data de distribuição</span><input type="date" value={form.data_distribuicao} onChange={(event) => setForm({ ...form, data_distribuicao: event.target.value })} /></label>
            <label className="form-field form-field--full"><span>Observações</span><textarea rows={3} value={form.observacoes} onChange={(event) => setForm({ ...form, observacoes: event.target.value })} /></label>
            <label className="form-field form-field--full"><span>Petição inicial</span><input type="file" accept=".pdf,.doc,.docx" onChange={(event) => setForm({ ...form, arquivo: event.target.files?.[0] ?? null })} /></label>
          </div>
          <div className="form-actions"><button className="button button--secondary" type="button" onClick={() => setModalOpen(false)} disabled={busy}>Cancelar</button><button className="button button--primary" type="submit" disabled={busy}>{busy ? 'Salvando...' : 'Salvar processo'}</button></div>
        </form>
      </Modal>

      <ConfirmDialog open={Boolean(deleting)} title="Excluir processo" message={`Deseja excluir o processo ${deleting?.numero_cnj ?? ''}? Os eventos vinculados serão mantidos sem o processo.`} busy={busy} onCancel={() => setDeleting(null)} onConfirm={handleDelete} />
    </div>
  );
};

export default Processos;
