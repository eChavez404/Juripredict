import { ArrowUpRight, Gauge, TrendingUp } from 'lucide-react';
import MetricCard from '../ui/MetricCard';
import type { AgenteResultado, AgenteSituacao } from '../../types';

const SITUACOES: Record<AgenteSituacao, { rotulo: string; cor: string }> = {
  atendido: { rotulo: 'Atendido', cor: 'green' },
  parcial: { rotulo: 'Parcial', cor: 'yellow' },
  ausente: { rotulo: 'Ausente', cor: 'red' },
  nao_aplicavel: { rotulo: 'Não se aplica', cor: 'gray' },
};

const Lista = ({ titulo, itens }: { titulo: string; itens: string[] }) => (itens.length ? (
  <article className="panel panel--padded">
    <div className="section-heading"><h2>{titulo}</h2></div>
    <ul className="agente-lista">{itens.map((item) => <li key={item}>{item}</li>)}</ul>
  </article>
) : null);

const AnaliseCompleta = ({ resultado }: { resultado: AgenteResultado }) => {
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
        <div className="section-heading"><h2>Casos parecidos: o que foi deferido e o que não foi</h2></div>
        {casos.length ? (
          <ul className="agente-itens">
            {casos.map((caso) => {
              const comparacao = comparacoes.get(caso.id_sentenca);
              return (
                <li key={caso.id_sentenca}>
                  <strong>
                    {caso.numero_cnj || caso.id_sentenca}{' '}
                    {caso.resultado && (
                      <span className={`status-badge status-badge--${caso.resultado === 'deferido' ? 'green' : 'red'}`}>
                        {caso.resultado === 'deferido' ? 'Deferido' : 'Indeferido'}
                      </span>
                    )}
                  </strong>
                  <small>
                    {[caso.tipo_documento, caso.orgao_julgador, caso.data_julgamento, `similaridade ${caso.similaridade.toFixed(2)}`]
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

export default AnaliseCompleta;
