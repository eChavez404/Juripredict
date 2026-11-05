import { useEffect, useState, type CSSProperties, type ElementType } from 'react';
import { BarChart3, Download, Sparkles, Target, TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ProtectedContent from '../components/auth/ProtectedContent';
import ProcessosDaTaxaModal from '../components/jurimetria/ProcessosDaTaxaModal';
import ChartTooltip from '../components/ui/ChartTooltip';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import { CAPABILITIES } from '../features/escritorios/types';
import { getApiError } from '../services/api';
import { jurimetriaService, type FiltrosJurimetria } from '../services/juripredict';
import type { IntervaloPercentual, JurimetriaData } from '../types';

const chartColors = { green: '#72a888', yellow: '#d2aa61', red: '#c87979' };

type AnalyticsKpiProps = { icon: ElementType; value: string; label: string; color: string };

const AnalyticsKpi = ({ icon: Icon, value, label, color }: AnalyticsKpiProps) => (
  <article className="panel analytics-kpi" style={{ '--kpi-color': color } as CSSProperties}>
    <span className="analytics-kpi__icon"><Icon size={22} aria-hidden="true" /></span>
    <div><strong>{value}</strong><p>{label}</p></div>
  </article>
);

type LinhaComparacao = {
  chave: string;
  rotulo: string;
  total: number;
  favoravel: number | null;
  intervalo_favoravel: IntervaloPercentual | null;
  motivo: string | null;
  filtros: FiltrosJurimetria;
};

const taxaDaLinha = (linha: LinhaComparacao) => (linha.favoravel === null || !linha.intervalo_favoravel
  ? 'Sem taxa: amostra insuficiente'
  : `${linha.favoravel}% (de ${linha.intervalo_favoravel.min}% a ${linha.intervalo_favoravel.max}%)`);

const JurimetriaConteudo = () => {
  const [data, setData] = useState<JurimetriaData | null>(null);
  const [error, setError] = useState('');
  const [area, setArea] = useState('');
  const [ano, setAno] = useState('');
  const [exportando, setExportando] = useState(false);
  const [recorte, setRecorte] = useState<{ titulo: string; filtros: FiltrosJurimetria } | null>(null);

  useEffect(() => {
    let ativo = true;
    jurimetriaService.get({ area, ano })
      .then((resposta) => { if (ativo) { setData(resposta); setError(''); } })
      .catch((requestError) => { if (ativo) setError(getApiError(requestError)); });
    return () => { ativo = false; };
  }, [area, ano]);

  const exportar = async () => {
    setExportando(true);
    setError('');
    try {
      await jurimetriaService.exportar({ area, ano });
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setExportando(false);
    }
  };

  if (error && !data) return <div className="page"><Feedback type="error">{error}</Feedback></div>;
  if (!data) return <div className="page"><div className="panel empty-state">Calculando indicadores...</div></div>;

  const rotuloTaxa = data.intervalo_favoravel
    ? `Favoráveis ou acordos · IC 95%: ${data.intervalo_favoravel.min}% a ${data.intervalo_favoravel.max}%`
    : `Amostra insuficiente para uma taxa (mínimo de ${data.piso_amostra} processos)`;
  // Só vara com amostra entra no gráfico, e o n aparece no rótulo. As demais
  // ficam listadas abaixo: sumir com elas esconderia o que não se pode afirmar.
  const varasSuficientes = data.por_vara.filter((item) => item.suficiente);
  const varasComTaxa = varasSuficientes
    .slice(0, 8)
    .map((item) => ({ ...item, rotulo: `${item.vara} (n=${item.total})` }));
  const varasSemAmostra = data.por_vara.filter((item) => !item.suficiente);

  const linhasVara: LinhaComparacao[] = data.por_vara.map((item) => ({
    ...item, chave: `vara-${item.vara}`, rotulo: item.vara, filtros: { area, ano, vara: item.vara },
  }));
  const linhasAno: LinhaComparacao[] = data.por_ano.map((item) => ({
    ...item,
    chave: `ano-${item.ano ?? 'sem'}`,
    rotulo: item.ano === null ? 'Sem data de distribuição' : String(item.ano),
    filtros: { area, ano: item.ano === null ? 'sem_data' : String(item.ano) },
  }));

  const tabelaComparacao = (titulo: string, cabecalho: string, linhas: LinhaComparacao[]) => (
    <article className="panel panel--padded">
      <div className="section-heading"><div><h2>{titulo}</h2></div></div>
      <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>{cabecalho}</th><th>Concluídos (n)</th><th>Taxa e intervalo de confiança</th><th>Conferir</th></tr></thead>
          <tbody>
            {linhas.map((linha) => (
              <tr key={linha.chave}>
                <td>{linha.rotulo}</td>
                <td>{linha.total}</td>
                <td>{taxaDaLinha(linha)}</td>
                <td>
                  <button className="button button--secondary button--small" type="button" aria-label={`Ver processos: ${linha.rotulo}`} onClick={() => setRecorte({ titulo: linha.rotulo, filtros: linha.filtros })}>
                    Ver processos
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );

  const resultData = data.resultados.map((item, index) => ({ ...item, fill: [chartColors.green, chartColors.yellow, chartColors.red][index] }));

  return (
    <div className="page">
      <PageHeader
        eyebrow="Inteligência jurídica"
        title="Jurimetria estratégica"
        description="Indicadores calculados a partir dos resultados cadastrados na sua própria carteira."
        backTo="/"
        action={(
          <button className="button button--secondary" type="button" onClick={() => void exportar()} disabled={exportando}>
            <Download size={17} /> {exportando ? 'Gerando...' : 'Exportar CSV'}
          </button>
        )}
      />

      {error && <Feedback type="error">{error}</Feedback>}

      <div className="panel jurimetria-filtros" role="group" aria-label="Filtros da análise">
        <label className="form-field">
          <span>Área</span>
          <select value={area} onChange={(event) => setArea(event.target.value)}>
            <option value="">Todas</option>
            {data.opcoes.areas.map((item) => <option value={item.valor} key={item.valor}>{item.rotulo}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Ano de distribuição</span>
          <select value={ano} onChange={(event) => setAno(event.target.value)}>
            <option value="">Todos</option>
            {data.opcoes.anos.map((item) => <option value={item} key={item}>{item}</option>)}
            <option value="sem_data">Sem data</option>
          </select>
        </label>
        {data.total_analisados > 0 && (
          <button className="button button--secondary button--small jurimetria-filtros__ver" type="button" onClick={() => setRecorte({ titulo: 'Recorte selecionado', filtros: { area, ano } })}>
            Ver os {data.total_analisados} {data.total_analisados === 1 ? 'processo' : 'processos'} do recorte
          </button>
        )}
      </div>

      <section className="grid jurimetria-metrics" aria-label="Indicadores de jurimetria">
        <AnalyticsKpi icon={BarChart3} value={data.taxa_favoravel === null ? '—' : `${data.taxa_favoravel}%`} label={rotuloTaxa} color={chartColors.green} />
        <AnalyticsKpi icon={Target} value={String(data.total_analisados)} label="Processos concluídos analisados" color={chartColors.red} />
        <AnalyticsKpi icon={TrendingUp} value={String(data.processos_ativos)} label="Processos ativos na carteira" color={chartColors.yellow} />
      </section>

      <section className="grid jurimetria-charts" aria-label="Análises estatísticas">
        <article className="panel panel--padded chart-container">
          <div className="section-heading"><div><h2>Resultados por vara</h2><p>Varas com ao menos {data.piso_amostra} processos concluídos</p></div></div>
          {varasComTaxa.length ? (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={varasComTaxa} layout="vertical" margin={{ top: 4, right: 8, left: 5, bottom: 0 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e4eff1" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} axisLine={false} tickLine={false} tick={{ fill: '#8da0a6', fontSize: 10 }} />
                <YAxis dataKey="rotulo" type="category" width={150} axisLine={false} tickLine={false} tick={{ fill: '#688088', fontSize: 10 }} />
                <Tooltip content={<ChartTooltip suffix="%" />} cursor={{ fill: '#f5fafb' }} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ color: '#688088', fontSize: '11px', paddingTop: '12px' }} />
                <Bar dataKey="favoravel" name="Favorável/acordo" stackId="resultado" fill={chartColors.green} maxBarSize={22} />
                <Bar dataKey="desfavoravel" name="Desfavorável" stackId="resultado" fill={chartColors.red} radius={[0, 6, 6, 0]} maxBarSize={22} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="empty-state">{varasSemAmostra.length ? 'Nenhuma vara tem amostra suficiente ainda.' : 'Finalize processos e informe seus resultados para preencher este gráfico.'}</p>}
          {varasSemAmostra.length > 0 && (
            <div className="amostra-insuficiente">
              <strong>Sem amostra suficiente para taxa</strong>
              <ul>
                {varasSemAmostra.map((item) => <li key={item.vara}>{item.vara}: {item.total} {item.total === 1 ? 'processo' : 'processos'} (mínimo de {data.piso_amostra})</li>)}
              </ul>
            </div>
          )}
        </article>

        <article className="panel panel--padded chart-container">
          <div className="section-heading"><div><h2>Distribuição dos resultados</h2><p>Volume por tipo de encerramento</p></div></div>
          {data.total_analisados ? (
            <ResponsiveContainer width="100%" height={320}>
              <RadialBarChart cx="50%" cy="46%" innerRadius="20%" outerRadius="82%" data={resultData}>
                <RadialBar dataKey="value" background={{ fill: '#eef5f6' }} cornerRadius={6} />
                <Legend iconSize={8} iconType="circle" wrapperStyle={{ color: '#688088', fontSize: '11px' }} />
                <Tooltip content={<ChartTooltip />} />
              </RadialBarChart>
            </ResponsiveContainer>
          ) : <p className="empty-state">Ainda não há resultados para analisar.</p>}
        </article>
      </section>

      {(linhasVara.length > 0 || linhasAno.length > 0) && (
        <section className="jurimetria-comparacao" aria-label="Comparação por vara e por ano">
          {linhasVara.length > 0 && tabelaComparacao('Comparar varas', 'Vara', linhasVara)}
          {linhasAno.length > 0 && tabelaComparacao('Comparar períodos', 'Ano de distribuição', linhasAno)}
          <p className="jurimetria-comparacao__nota">Intervalos que se sobrepõem não permitem afirmar que um grupo difere do outro.</p>
        </section>
      )}

      <section className="panel ai-analysis">
        <span className="ai-analysis__icon"><Sparkles size={21} aria-hidden="true" /></span>
        <div><h2>Leitura da carteira</h2><p>{data.insight}</p></div>
      </section>

      <ProcessosDaTaxaModal recorte={recorte} onClose={() => setRecorte(null)} />
    </div>
  );
};

const Jurimetria = () => (
  <ProtectedContent capability={CAPABILITIES.jurimetriaVisualizar}>
    <JurimetriaConteudo />
  </ProtectedContent>
);

export default Jurimetria;
