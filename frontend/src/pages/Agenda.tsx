import { useCallback, useEffect, useMemo, useState, type CSSProperties, type ElementType, type FormEvent } from 'react';
import { AlertTriangle, CalendarDays, Check, CheckCircle2, ChevronLeft, ChevronRight, Clock3, Pencil, Plus, Trash2 } from 'lucide-react';
import ConfirmDialog from '../components/ui/ConfirmDialog';
import Feedback from '../components/ui/Feedback';
import Modal from '../components/ui/Modal';
import PageHeader from '../components/ui/PageHeader';
import { getApiError } from '../services/api';
import { eventoService, processoService } from '../services/juripredict';
import type { EventoAgenda, EventoTipo, Processo } from '../types';

const nomesDias = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];

const eventTypes: Record<EventoTipo, { icon: ElementType; color: string; label: string }> = {
  AUDIENCIA: { icon: CalendarDays, color: '#58a7b7', label: 'Audiência' },
  PRAZO: { icon: AlertTriangle, color: '#c87979', label: 'Prazo' },
  REUNIAO: { icon: Clock3, color: '#72a888', label: 'Reunião' },
  OUTRO: { icon: CalendarDays, color: '#d2aa61', label: 'Outro' },
};

type EventoForm = {
  titulo: string;
  tipo: EventoTipo;
  inicio: string;
  fim: string;
  processo: string;
  local: string;
  descricao: string;
  concluido: boolean;
};

const dateKey = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const toDateTimeInput = (value?: string) => {
  const date = value ? new Date(value) : new Date();
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${dateKey(date)}T${hours}:${minutes}`;
};

const startOfWeek = (value: Date) => {
  const result = new Date(value);
  const day = result.getDay() || 7;
  result.setHours(0, 0, 0, 0);
  result.setDate(result.getDate() - day + 1);
  return result;
};

const emptyForm = (): EventoForm => ({
  titulo: '',
  tipo: 'PRAZO',
  inicio: toDateTimeInput(),
  fim: '',
  processo: '',
  local: '',
  descricao: '',
  concluido: false,
});

const Agenda = () => {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [eventos, setEventos] = useState<EventoAgenda[]>([]);
  const [processos, setProcessos] = useState<Processo[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<EventoAgenda | null>(null);
  const [deleting, setDeleting] = useState<EventoAgenda | null>(null);
  const [form, setForm] = useState<EventoForm>(emptyForm);

  const weekDays = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const date = new Date(weekStart);
    date.setDate(date.getDate() + index);
    return date;
  }), [weekStart]);

  const loadData = useCallback(async () => {
    const end = new Date(weekStart);
    end.setDate(end.getDate() + 6);
    try {
      const [eventData, processData] = await Promise.all([
        eventoService.list(dateKey(weekStart), dateKey(end)),
        processoService.list(),
      ]);
      setEventos(eventData);
      setProcessos(processData);
      setError('');
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setLoading(false);
    }
  }, [weekStart]);

  useEffect(() => { void loadData(); }, [loadData]);

  const openCreate = () => {
    const initial = emptyForm();
    initial.inicio = `${dateKey(weekStart)}T09:00`;
    setEditing(null);
    setForm(initial);
    setFormError('');
    setModalOpen(true);
  };

  const openEdit = (evento: EventoAgenda) => {
    setEditing(evento);
    setForm({
      titulo: evento.titulo,
      tipo: evento.tipo,
      inicio: toDateTimeInput(evento.inicio),
      fim: evento.fim ? toDateTimeInput(evento.fim) : '',
      processo: evento.processo?.toString() ?? '',
      local: evento.local,
      descricao: evento.descricao,
      concluido: evento.concluido,
    });
    setFormError('');
    setModalOpen(true);
  };

  const serializeForm = () => ({
    titulo: form.titulo,
    tipo: form.tipo,
    inicio: new Date(form.inicio).toISOString(),
    fim: form.fim ? new Date(form.fim).toISOString() : null,
    processo: form.processo ? Number(form.processo) : null,
    local: form.local,
    descricao: form.descricao,
    concluido: form.concluido,
  });

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setFormError('');
    try {
      if (editing) await eventoService.update(editing.id, serializeForm());
      else await eventoService.create(serializeForm());
      setModalOpen(false);
      await loadData();
    } catch (requestError) {
      setFormError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  const toggleComplete = async (evento: EventoAgenda) => {
    setError('');
    try {
      await eventoService.update(evento.id, { concluido: !evento.concluido });
      await loadData();
    } catch (requestError) {
      setError(getApiError(requestError));
    }
  };

  const handleDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    try {
      await eventoService.remove(deleting.id);
      setDeleting(null);
      await loadData();
    } catch (requestError) {
      setError(getApiError(requestError));
      setDeleting(null);
    } finally {
      setBusy(false);
    }
  };

  const moveWeek = (amount: number) => {
    const next = new Date(weekStart);
    next.setDate(next.getDate() + amount * 7);
    setLoading(true);
    setWeekStart(next);
  };

  const audiencias = eventos.filter((event) => event.tipo === 'AUDIENCIA' && !event.concluido).length;
  const prazos = eventos.filter((event) => event.tipo === 'PRAZO' && !event.concluido).length;
  const concluidos = eventos.filter((event) => event.concluido).length;

  return (
    <div className="page">
      <PageHeader
        eyebrow="Organização"
        title="Agenda e prazos"
        description="Gerencie compromissos, audiências e vencimentos do escritório."
        action={<button className="button button--primary" type="button" onClick={openCreate}><Plus size={17} /> Novo compromisso</button>}
      />

      {error && <Feedback type="error">{error}</Feedback>}

      <div className="agenda-toolbar">
        <div className="agenda-summary" aria-label="Resumo da semana">
          <span><CalendarDays size={14} /> {audiencias} audiências</span>
          <span><AlertTriangle size={14} /> {prazos} prazos</span>
          <span><CheckCircle2 size={14} /> {concluidos} concluídos</span>
        </div>
        <div className="week-navigation">
          <button className="action-button" type="button" aria-label="Semana anterior" onClick={() => moveWeek(-1)}><ChevronLeft size={16} /></button>
          <strong>{weekDays[0].toLocaleDateString('pt-BR')} — {weekDays[6].toLocaleDateString('pt-BR')}</strong>
          <button className="action-button" type="button" aria-label="Próxima semana" onClick={() => moveWeek(1)}><ChevronRight size={16} /></button>
        </div>
      </div>

      {loading ? <div className="panel empty-state">Carregando agenda...</div> : (
        <section className="grid agenda-week" aria-label="Agenda da semana atual">
          {weekDays.map((day, index) => {
            const dayEvents = eventos.filter((evento) => dateKey(new Date(evento.inicio)) === dateKey(day));
            return (
              <article className="panel day-column" key={dateKey(day)}>
                <header className="day-column__header"><div><h2>{nomesDias[index]}</h2><small>{day.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}</small></div><span>{dayEvents.length}</span></header>
                <div className="event-list">
                  {dayEvents.map((evento) => {
                    const { icon: Icon, color } = eventTypes[evento.tipo];
                    return (
                      <div className={`event-card${evento.concluido ? ' event-card--done' : ''}`} key={evento.id} style={{ '--event-color': color } as CSSProperties}>
                        <div className="event-card__time">{evento.concluido ? <CheckCircle2 size={13} /> : <Icon size={13} />}{new Date(evento.inicio).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</div>
                        <h3>{evento.titulo}</h3>
                        {evento.processo_numero && <p>{evento.processo_numero}<br />{evento.cliente_nome}</p>}
                        {evento.local && <p>{evento.local}</p>}
                        <div className="event-card__actions">
                          <button type="button" aria-label="Concluir compromisso" onClick={() => void toggleComplete(evento)}><Check size={13} /></button>
                          <button type="button" aria-label="Editar compromisso" onClick={() => openEdit(evento)}><Pencil size={13} /></button>
                          <button type="button" aria-label="Excluir compromisso" onClick={() => setDeleting(evento)}><Trash2 size={13} /></button>
                        </div>
                      </div>
                    );
                  })}
                  {dayEvents.length === 0 && <p className="day-column__empty">Nenhum compromisso</p>}
                </div>
              </article>
            );
          })}
        </section>
      )}

      <Modal open={modalOpen} title={editing ? 'Editar compromisso' : 'Novo compromisso'} onClose={() => !busy && setModalOpen(false)}>
        <form className="entity-form" onSubmit={handleSubmit}>
          {formError && <Feedback type="error">{formError}</Feedback>}
          <div className="form-grid">
            <label className="form-field form-field--full"><span>Título</span><input value={form.titulo} onChange={(event) => setForm({ ...form, titulo: event.target.value })} required /></label>
            <label className="form-field"><span>Tipo</span><select value={form.tipo} onChange={(event) => setForm({ ...form, tipo: event.target.value as EventoTipo })}>{Object.entries(eventTypes).map(([value, config]) => <option value={value} key={value}>{config.label}</option>)}</select></label>
            <label className="form-field"><span>Processo relacionado</span><select value={form.processo} onChange={(event) => setForm({ ...form, processo: event.target.value })}><option value="">Sem processo</option>{processos.map((processo) => <option value={processo.id} key={processo.id}>{processo.numero_cnj} — {processo.cliente_nome}</option>)}</select></label>
            <label className="form-field"><span>Início</span><input type="datetime-local" value={form.inicio} onChange={(event) => setForm({ ...form, inicio: event.target.value })} required /></label>
            <label className="form-field"><span>Término</span><input type="datetime-local" value={form.fim} onChange={(event) => setForm({ ...form, fim: event.target.value })} /></label>
            <label className="form-field form-field--full"><span>Local ou link</span><input value={form.local} onChange={(event) => setForm({ ...form, local: event.target.value })} /></label>
            <label className="form-field form-field--full"><span>Descrição</span><textarea rows={3} value={form.descricao} onChange={(event) => setForm({ ...form, descricao: event.target.value })} /></label>
            <label className="checkbox-label form-field--full"><input type="checkbox" checked={form.concluido} onChange={(event) => setForm({ ...form, concluido: event.target.checked })} /> Compromisso concluído</label>
          </div>
          <div className="form-actions"><button className="button button--secondary" type="button" onClick={() => setModalOpen(false)} disabled={busy}>Cancelar</button><button className="button button--primary" type="submit" disabled={busy}>{busy ? 'Salvando...' : 'Salvar compromisso'}</button></div>
        </form>
      </Modal>

      <ConfirmDialog open={Boolean(deleting)} title="Excluir compromisso" message={`Deseja excluir “${deleting?.titulo ?? ''}”?`} busy={busy} onCancel={() => setDeleting(null)} onConfirm={handleDelete} />
    </div>
  );
};

export default Agenda;
