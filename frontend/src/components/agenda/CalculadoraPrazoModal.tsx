import { useEffect, useRef, useState, type FormEvent } from 'react';
import { CalendarPlus, Calculator } from 'lucide-react';
import { getApiError } from '../../services/api';
import { eventoService, prazoService } from '../../services/juripredict';
import type { DiaDaMemoria, PrazoCalculado, PrazoTipo, Processo } from '../../types';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';

type CalculadoraPrazoModalProps = {
  open: boolean;
  onClose: () => void;
  /** Processo já definido (vindo de um andamento). Sem ele, a pessoa escolhe em `processos`. */
  processo?: Processo | null;
  processos?: Processo[];
  dataBase?: string;
  titulo?: string;
  onCriado?: () => void;
};

const AREAS: Record<string, string> = { TRABALHISTA: 'Trabalhista (CLT)', CIVEL: 'Cível (CPC)' };
const TIPOS: Record<PrazoTipo, string> = {
  INTIMACAO: 'Ciência direta do ato',
  PUBLICACAO_DIARIO: 'Disponibilização no diário eletrônico',
};
const DIAS_COMUNS = [5, 8, 15];

// Meio-dia: a data pura seria lida como UTC e, no Brasil, recuaria para o dia anterior.
const dataLocal = (iso: string) => new Date(`${iso}T12:00:00`);
const formatarDia = (iso: string) => dataLocal(iso).toLocaleDateString('pt-BR');
const formatarDiaExtenso = (iso: string) => dataLocal(iso).toLocaleDateString('pt-BR', {
  weekday: 'long', day: '2-digit', month: 'long', year: 'numeric',
});

const memoriaDoCalculo = (resultado: PrazoCalculado, informados: DiaDaMemoria[]) => [
  `Prazo de ${resultado.dias} ${resultado.dias === 1 ? 'dia útil' : 'dias úteis'}.`,
  `${TIPOS[resultado.tipo]}: ${formatarDia(resultado.data_base)}.`,
  `Primeiro dia contado: ${formatarDia(resultado.primeiro_dia_contado)}.`,
  `Vencimento: ${formatarDia(resultado.vencimento)}.`,
  `Fundamento: ${resultado.fundamento}.`,
  informados.length
    ? `Dias sem expediente informados: ${informados.map((dia) => formatarDia(dia.data)).join(', ')}.`
    : 'Nenhum dia sem expediente informado além dos feriados nacionais.',
  'Cálculo de apoio: confira o calendário do tribunal.',
].join(' ');

const CalculadoraPrazoModal = ({
  open, onClose, processo = null, processos = [], dataBase = '', titulo: tituloInicial = '', onCriado,
}: CalculadoraPrazoModalProps) => {
  const [data, setData] = useState(dataBase);
  const [dias, setDias] = useState('8');
  const [tipo, setTipo] = useState<PrazoTipo>('INTIMACAO');
  const [areaEscolhida, setAreaEscolhida] = useState('TRABALHISTA');
  const [processoId, setProcessoId] = useState('');
  const [titulo, setTitulo] = useState(tituloInicial);
  const [informados, setInformados] = useState<DiaDaMemoria[]>([]);
  const [outroDia, setOutroDia] = useState('');
  const [resultado, setResultado] = useState<PrazoCalculado | null>(null);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const ultimoCalculo = useRef(0);

  useEffect(() => {
    if (!open) return;
    setData(dataBase);
    setDias('8');
    setTipo('INTIMACAO');
    setAreaEscolhida('TRABALHISTA');
    setProcessoId('');
    setTitulo(tituloInicial);
    setInformados([]);
    setOutroDia('');
    setResultado(null);
    setErro('');
  }, [open, dataBase, tituloInicial]);

  const processoAtual = processo ?? processos.find((item) => String(item.id) === processoId) ?? null;
  // A área do processo manda: contar um prazo penal em dias úteis seria um erro grave.
  const area = processoAtual?.area ?? areaEscolhida;
  const areaCalculavel = area in AREAS;

  // Qualquer mudança invalida o resultado: não se pode gravar uma data de outro cálculo.
  const invalidar = () => {
    ultimoCalculo.current += 1;
    setResultado(null);
    setErro('');
  };

  const calcular = async (dias_informados: DiaDaMemoria[]) => {
    const atual = ++ultimoCalculo.current;
    setBusy(true);
    setErro('');
    try {
      const resposta = await prazoService.calcular({
        data_base: data,
        dias: Number(dias),
        tipo,
        area,
        suspensoes: dias_informados.map((dia) => dia.data),
      });
      if (atual === ultimoCalculo.current) setResultado(resposta);
    } catch (requestError) {
      if (atual === ultimoCalculo.current) {
        setResultado(null);
        setErro(getApiError(requestError));
      }
    } finally {
      if (atual === ultimoCalculo.current) setBusy(false);
    }
  };

  const handleCalcular = (event: FormEvent) => {
    event.preventDefault();
    void calcular(informados);
  };

  const alternarDia = (dia: DiaDaMemoria) => {
    const proximos = informados.some((item) => item.data === dia.data)
      ? informados.filter((item) => item.data !== dia.data)
      : [...informados, dia];
    setInformados(proximos);
    void calcular(proximos);
  };

  const adicionarOutroDia = () => {
    if (!outroDia || informados.some((item) => item.data === outroDia)) return;
    const proximos = [...informados, { data: outroDia, motivo: 'Informado por você' }];
    setInformados(proximos);
    setOutroDia('');
    void calcular(proximos);
  };

  const adicionarNaAgenda = async () => {
    if (!resultado) return;
    setBusy(true);
    setErro('');
    try {
      await eventoService.create({
        titulo: titulo.trim(),
        tipo: 'PRAZO',
        // 9h do vencimento: o lembrete sai 24 horas antes, ainda em horário de trabalho
        inicio: new Date(`${resultado.vencimento}T09:00:00`).toISOString(),
        fim: null,
        processo: processoAtual?.id ?? null,
        local: '',
        descricao: memoriaDoCalculo(resultado, informados),
        concluido: false,
      });
      onCriado?.();
      onClose();
    } catch (requestError) {
      setErro(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  // Por data: enquanto o novo cálculo não volta, um dia recém-marcado está nas duas listas.
  const diasParaConferir = [...new Map(
    [...(resultado?.dias_a_conferir ?? []), ...informados].map((dia) => [dia.data, dia]),
  ).values()].sort((a, b) => a.data.localeCompare(b.data));

  return (
    <Modal
      open={open}
      title="Calcular prazo"
      description="Contagem em dias úteis, com a memória do cálculo."
      size="large"
      onClose={() => { if (!busy) onClose(); }}
    >
      <form className="entity-form" onSubmit={handleCalcular}>
        {erro && <Feedback type="error">{erro}</Feedback>}
        {!areaCalculavel && (
          <Feedback type="info">Este processo é de área com contagem própria. A calculadora atende as áreas trabalhista e cível.</Feedback>
        )}
        <div className="form-grid">
          {!processo && processos.length > 0 && (
            <label className="form-field form-field--full">
              <span>Processo relacionado</span>
              <select value={processoId} onChange={(event) => { setProcessoId(event.target.value); invalidar(); }}>
                <option value="">Sem processo</option>
                {processos.map((item) => <option value={item.id} key={item.id}>{item.numero_cnj} — {item.cliente_nome}</option>)}
              </select>
            </label>
          )}
          <label className="form-field">
            <span>Data</span>
            <input type="date" value={data} required onChange={(event) => { setData(event.target.value); invalidar(); }} />
          </label>
          <label className="form-field">
            <span>Como a ciência ocorreu</span>
            <select value={tipo} onChange={(event) => { setTipo(event.target.value as PrazoTipo); invalidar(); }}>
              {Object.entries(TIPOS).map(([valor, rotulo]) => <option value={valor} key={valor}>{rotulo}</option>)}
            </select>
          </label>
          <label className="form-field">
            <span>Prazo em dias úteis</span>
            <input type="number" min={1} max={365} value={dias} required onChange={(event) => { setDias(event.target.value); invalidar(); }} />
          </label>
          <label className="form-field">
            <span>Área</span>
            <select
              value={areaCalculavel ? area : ''}
              disabled={Boolean(processoAtual)}
              onChange={(event) => { setAreaEscolhida(event.target.value); invalidar(); }}
            >
              {!areaCalculavel && <option value="">Sem cálculo disponível</option>}
              {Object.entries(AREAS).map(([valor, rotulo]) => <option value={valor} key={valor}>{rotulo}</option>)}
            </select>
          </label>
          <div className="prazo-atalhos form-field--full">
            {DIAS_COMUNS.map((valor) => (
              <button className="button button--secondary button--small" type="button" key={valor} onClick={() => { setDias(String(valor)); invalidar(); }}>
                {valor} dias
              </button>
            ))}
          </div>
        </div>

        {!resultado && (
          <div className="form-actions">
            <button className="button button--secondary" type="button" onClick={onClose} disabled={busy}>Cancelar</button>
            <button className="button button--primary" type="submit" disabled={busy || !areaCalculavel}>
              <Calculator size={16} /> {busy ? 'Calculando...' : 'Calcular'}
            </button>
          </div>
        )}
      </form>

      {resultado && (
        <section className="prazo-resultado" aria-label="Resultado do cálculo">
          <p className="prazo-resultado__vencimento">
            <small>Vencimento</small>
            <strong>{formatarDiaExtenso(resultado.vencimento)}</strong>
          </p>

          {diasParaConferir.length > 0 && (
            <fieldset className="prazo-conferir" disabled={busy}>
              <legend>Confira no calendário do tribunal</legend>
              <p>Estes dias costumam ter suspensão, mas dependem de ato do tribunal. Enquanto não marcados, contam como úteis, o que nunca adia a data.</p>
              {diasParaConferir.map((dia) => (
                <label className="checkbox-label" key={dia.data}>
                  <input
                    type="checkbox"
                    checked={informados.some((item) => item.data === dia.data)}
                    onChange={() => alternarDia(dia)}
                  />
                  {formatarDia(dia.data)} · {dia.motivo}: sem expediente
                </label>
              ))}
            </fieldset>
          )}

          <div className="prazo-outro-dia">
            <label className="form-field">
              <span>Outro dia sem expediente (feriado local, ponto facultativo)</span>
              <input type="date" value={outroDia} onChange={(event) => setOutroDia(event.target.value)} />
            </label>
            <button className="button button--secondary button--small" type="button" onClick={adicionarOutroDia} disabled={busy || !outroDia}>Adicionar</button>
          </div>

          <details className="prazo-memoria">
            <summary>Memória do cálculo</summary>
            <ul>
              <li>Base: {formatarDia(resultado.data_base)} ({TIPOS[resultado.tipo].toLowerCase()})</li>
              <li>Primeiro dia contado: {formatarDia(resultado.primeiro_dia_contado)}</li>
              <li>Fins de semana não contados: {resultado.fins_de_semana_nao_contados} {resultado.fins_de_semana_nao_contados === 1 ? 'dia' : 'dias'}</li>
              {resultado.dias_nao_contados.map((dia) => <li key={dia.data}>Não contado: {formatarDia(dia.data)} ({dia.motivo})</li>)}
              <li>Fundamento: {resultado.fundamento}</li>
            </ul>
          </details>

          {resultado.ressalvas.map((ressalva) => <p className="prazo-ressalva" key={ressalva}>{ressalva}</p>)}

          <label className="form-field">
            <span>Título na agenda</span>
            <input value={titulo} onChange={(event) => setTitulo(event.target.value)} placeholder="Ex.: Recurso ordinário" />
          </label>

          <div className="form-actions">
            <button className="button button--secondary" type="button" onClick={onClose} disabled={busy}>Fechar</button>
            <button className="button button--primary" type="button" onClick={() => void adicionarNaAgenda()} disabled={busy || !titulo.trim()}>
              <CalendarPlus size={16} /> {busy ? 'Aguarde...' : 'Adicionar à agenda'}
            </button>
          </div>
        </section>
      )}
    </Modal>
  );
};

export default CalculadoraPrazoModal;
