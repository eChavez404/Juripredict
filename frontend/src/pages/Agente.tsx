import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowUpRight, Gauge, Scale, TrendingUp } from 'lucide-react';
import ProtectedContent from '../components/auth/ProtectedContent';
import Feedback from '../components/ui/Feedback';
import MetricCard from '../components/ui/MetricCard';
import PageHeader from '../components/ui/PageHeader';
import { useAuth } from '../contexts/auth';
import { CAPABILITIES } from '../features/escritorios/types';
import { getApiError } from '../services/api';
import { agenteService } from '../services/juripredict';
import type { AgenteCaso, AgenteOpcoes, AgenteResultado, AgenteSituacao } from '../types';

const INTERVALO_MS = 2000;
// Acima do pior caso do agente: busca na base mais duas tentativas do modelo.
const LIMITE_MS = 6 * 60 * 1000;

const ETAPAS: Record<string, string> = {
  prepare_context: 'Separando os critérios do tema...',
  retrieve_cases: 'Procurando decisões parecidas na base...',
  analyze_case: 'Analisando o caso. Pode levar mais de um minuto...',
  measure_case: 'Calculando os índices...',
};

const SITUACOES: Record<AgenteSituacao, { rotulo: string; cor: string }> = {
  atendido: { rotulo: 'Atendido', cor: 'green' },
  parcial: { rotulo: 'Parcial', cor: 'yellow' },
  ausente: { rotulo: 'Ausente', cor: 'red' },
  nao_aplicavel: { rotulo: 'Não se aplica', cor: 'gray' },
};

const CASO_VAZIO: AgenteCaso = {
  tema: '', fase: '', relato: '', provas: [], orgao_julgador: '', duvida: '',
};

const esperar = (ms: number) => new Promise((resolve) => { setTimeout(resolve, ms); });

const Lista = ({ titulo, itens }: { titulo: string; itens: string[] }) => (itens.length ? (
  <article className="panel panel--padded">
    <div className="section-heading"><h2>{titulo}</h2></div>
    <ul className="agente-lista">{itens.map((item) => <li key={item}>{item}</li>)}</ul>
  </article>
) : null);

const Resultado = ({ resultado }: { resultado: AgenteResultado }) => {
  const { analise, catalogo, medicao, casos, suposicoes, disclaimer } = resultado;
  const criterios = new Map(catalogo.criterios.map((item) => [item.id, item]));
  const comparacoes = new Map(analise.casos_proximos.map((item) => [item.caso_id, item]));
  const nomeDoCaso = (id: string) => casos.find((item) => item.id_sentenca === id)?.numero_cnj || id;

  return (
    <section className="agente-resultado" aria-label="Resultado da análise">
      <article className="panel panel--padded">
        <div className="section-heading"><div><h2>{analise.titulo}</h2></div></div>
        <p className="agente-texto">{analise.resumo}</p>
      </article>

      <div className="grid jurimetria-metrics">
        <MetricCard label="Índice atual" value={String(medicao.indice_atual)} detail="de 100" icon={Gauge} tone="yellow" />
        <MetricCard label="Índice com as melhorias" value={String(medicao.indice_potencial)} detail="de 100" icon={TrendingUp} tone="green" />
        <MetricCard label="Ganho possível" value={`+${medicao.ganho}`} detail="pontos" icon={ArrowUpRight} />
      </div>
      <p className="field-hint">O índice mostra quanto do que o tema exige está demonstrado. Não é probabilidade de êxito.</p>

      <Lista titulo="Atenção" itens={medicao.alertas} />

      <article className="panel panel--padded">
        <div className="section-heading"><h2>Critérios avaliados</h2></div>
        <div className="table-scroll">
          <table className="data-table data-table--compacta">
            <thead><tr><th>Critério</th><th>Situação</th><th>Evidência</th></tr></thead>
            <tbody>
              {analise.criterios.map((item) => {
                const criterio = criterios.get(item.criterio_id);
                const situacao = SITUACOES[item.situacao];
                return (
                  <tr key={item.criterio_id}>
                    <td>
                      <strong>{criterio?.nome ?? item.criterio_id}</strong>
                      <p className="table-secondary">{criterio?.fundamentos.join(' · ')}</p>
                    </td>
                    <td><span className={`status-badge status-badge--${situacao.cor}`}>{situacao.rotulo}</span></td>
                    <td>{item.evidencia}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </article>

      <article className="panel panel--padded">
        <div className="section-heading"><h2>O que melhorar</h2></div>
        {analise.melhorias.length ? (
          <ul className="agente-itens">
            {analise.melhorias.map((item) => (
              <li key={`${item.criterio_id}-${item.acao}`}>
                <span className="eyebrow">{criterios.get(item.criterio_id)?.nome ?? item.criterio_id}</span>
                <strong>{item.acao}</strong>
                <p className="agente-texto">{item.justificativa}</p>
                {item.caso_ids.length > 0 && <small>Apoio: {item.caso_ids.map(nomeDoCaso).join(' · ')}</small>}
              </li>
            ))}
          </ul>
        ) : <p className="agente-texto">Nenhuma melhoria proposta.</p>}
      </article>

      <article className="panel panel--padded">
        <div className="section-heading"><h2>Casos mais próximos</h2></div>
        {casos.length ? (
          <ul className="agente-itens">
            {casos.map((caso) => {
              const comparacao = comparacoes.get(caso.id_sentenca);
              return (
                <li key={caso.id_sentenca}>
                  <strong>{caso.numero_cnj || caso.id_sentenca}</strong>
                  <small>
                    {[caso.tipo_documento, caso.orgao_julgador, caso.data_julgamento, caso.resultado, `similaridade ${caso.similaridade.toFixed(2)}`]
                      .filter(Boolean).join(' · ')}
                  </small>
                  {comparacao && (
                    <>
                      <p className="agente-texto"><b>Semelhanças:</b> {comparacao.semelhancas}</p>
                      <p className="agente-texto"><b>Diferenças:</b> {comparacao.diferencas}</p>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        ) : <p className="agente-texto">Nenhum caso próximo consultado.</p>}
      </article>

      <Lista titulo="Pontos fortes" itens={medicao.pontos_fortes} />
      <Lista titulo="Riscos" itens={analise.riscos} />
      <Lista titulo="Suposições" itens={suposicoes} />
      <p className="field-hint">{disclaimer} Critérios v{catalogo.versao}.</p>
    </section>
  );
};

const AgenteConteudo = () => {
  const [opcoes, setOpcoes] = useState<AgenteOpcoes | null>(null);
  const [caso, setCaso] = useState<AgenteCaso>(CASO_VAZIO);
  const [etapa, setEtapa] = useState('');
  const [resultado, setResultado] = useState<AgenteResultado | null>(null);
  const [erro, setErro] = useState('');
  const ativo = useRef(true);

  useEffect(() => {
    ativo.current = true;
    agenteService.opcoes()
      .then((resposta) => {
        if (!ativo.current) return;
        setOpcoes(resposta);
        setCaso((atual) => ({
          ...atual, tema: resposta.temas[0]?.value ?? '', fase: resposta.fases[0]?.value ?? '',
        }));
      })
      .catch((requestError) => { if (ativo.current) setErro(getApiError(requestError)); });
    return () => { ativo.current = false; };
  }, []);

  const mudar = (campos: Partial<AgenteCaso>) => setCaso((atual) => ({ ...atual, ...campos }));

  const alternarProva = (valor: string) => mudar({
    provas: caso.provas.includes(valor)
      ? caso.provas.filter((item) => item !== valor)
      : [...caso.provas, valor],
  });

  const analisar = async (event: FormEvent) => {
    event.preventDefault();
    setErro('');
    setResultado(null);
    setEtapa('prepare_context');
    try {
      const limite = Date.now() + LIMITE_MS;
      let analise = await agenteService.iniciar(caso);
      while (ativo.current && analise.status === 'running') {
        if (Date.now() > limite) throw new Error('tempo esgotado');
        setEtapa(analise.step ?? 'prepare_context');
        await esperar(INTERVALO_MS);
        if (ativo.current) analise = await agenteService.consultar(analise.id);
      }
      if (!ativo.current) return;
      if (analise.status === 'done' && analise.result) setResultado(analise.result);
      else setErro(analise.error ?? 'Não foi possível analisar o caso.');
    } catch (requestError) {
      if (ativo.current) {
        setErro(requestError instanceof Error && requestError.message === 'tempo esgotado'
          ? 'A análise demorou mais que o esperado. Tente novamente.'
          : getApiError(requestError));
      }
    } finally {
      if (ativo.current) setEtapa('');
    }
  };

  const analisando = etapa !== '';

  return (
    <div className="page">
      <PageHeader
        eyebrow="Inteligência jurídica"
        title="Agente de IA"
        description="Meça o caso, veja o que ainda dá para melhorar e compare com decisões do TRT da 16ª Região."
        backTo="/"
      />

      {erro && <Feedback type="error">{erro}</Feedback>}

      {opcoes && (
        <form className="panel panel--padded entity-form" onSubmit={(event) => void analisar(event)}>
          <Feedback type="info">
            O texto do caso é enviado a serviços de IA de terceiros. Não informe nomes das partes. CPF e CNPJ são mascarados antes do envio.
          </Feedback>
          <div className="form-grid">
            <label className="form-field">
              <span>Tema</span>
              <select value={caso.tema} required onChange={(event) => mudar({ tema: event.target.value })}>
                {opcoes.temas.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label className="form-field">
              <span>Fase do processo</span>
              <select value={caso.fase} required onChange={(event) => mudar({ fase: event.target.value })}>
                {opcoes.fases.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
              </select>
            </label>
            <label className="form-field form-field--full">
              <span>Relato do caso</span>
              <textarea
                className="agente-relato"
                value={caso.relato}
                required
                minLength={40}
                maxLength={12000}
                placeholder="Função, período, local, agente ou risco, EPI, o que a empresa alega..."
                onChange={(event) => mudar({ relato: event.target.value })}
              />
            </label>
            <fieldset className="prazo-conferir form-field--full">
              <legend>Provas disponíveis</legend>
              <div className="agente-provas">
                {opcoes.provas.map((item) => (
                  <label className="checkbox-label" key={item.value}>
                    <input type="checkbox" checked={caso.provas.includes(item.value)} onChange={() => alternarProva(item.value)} />
                    {item.label}
                  </label>
                ))}
              </div>
            </fieldset>
            <label className="form-field">
              <span>Órgão julgador (opcional)</span>
              <input value={caso.orgao_julgador} maxLength={200} placeholder="Ex.: 2ª Vara do Trabalho de São Luís" onChange={(event) => mudar({ orgao_julgador: event.target.value })} />
            </label>
            <label className="form-field">
              <span>Ponto que mais preocupa (opcional)</span>
              <input value={caso.duvida} maxLength={500} placeholder="Ex.: a empresa juntou fichas de EPI assinadas" onChange={(event) => mudar({ duvida: event.target.value })} />
            </label>
          </div>
          <div className="form-actions">
            <button className="button button--primary" type="submit" disabled={analisando}>
              <Scale size={16} aria-hidden="true" /> {analisando ? 'Analisando...' : 'Analisar caso'}
            </button>
          </div>
        </form>
      )}

      {analisando && <Feedback type="info">{ETAPAS[etapa] ?? 'Analisando...'}</Feedback>}
      {resultado && <Resultado resultado={resultado} />}
    </div>
  );
};

const Agente = () => {
  const { activeEscritorio } = useAuth();
  return (
    <ProtectedContent capability={CAPABILITIES.agenteUsar}>
      {/* A chave recomeça a tela ao trocar de escritório: o caso de um não fica à vista no outro. */}
      <AgenteConteudo key={activeEscritorio?.id} />
    </ProtectedContent>
  );
};

export default Agente;
