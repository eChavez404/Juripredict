import { useEffect, useState, type CSSProperties, type ElementType } from 'react';
import { BarChart3, Sparkles, Target, TrendingUp } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, Legend, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from '../components/ui/ChartTooltip';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import { getApiError } from '../services/api';
import { jurimetriaService } from '../services/juripredict';
import type { JurimetriaData } from '../types';

const chartColors = { green: '#72a888', yellow: '#d2aa61', red: '#c87979' };

type AnalyticsKpiProps = { icon: ElementType; value: string; label: string; color: string };

const AnalyticsKpi = ({ icon: Icon, value, label, color }: AnalyticsKpiProps) => (
  <article className="panel analytics-kpi" style={{ '--kpi-color': color } as CSSProperties}>
    <span className="analytics-kpi__icon"><Icon size={22} aria-hidden="true" /></span>
    <div><strong>{value}</strong><p>{label}</p></div>
  </article>
);

const Jurimetria = () => {
  const [data, setData] = useState<JurimetriaData | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    jurimetriaService.get().then(setData).catch((requestError) => setError(getApiError(requestError)));
  }, []);

  if (error) return <div className="page"><Feedback type="error">{error}</Feedback></div>;
  if (!data) return <div className="page"><div className="panel empty-state">Calculando indicadores...</div></div>;

  const resultData = data.resultados.map((item, index) => ({ ...item, fill: [chartColors.green, chartColors.yellow, chartColors.red][index] }));

  return (
    <div className="page">
      <PageHeader eyebrow="Inteligência jurídica" title="Jurimetria estratégica" description="Indicadores calculados a partir dos resultados cadastrados na sua própria carteira." />

      <section className="grid jurimetria-metrics" aria-label="Indicadores de jurimetria">
        <AnalyticsKpi icon={BarChart3} value={`${data.taxa_favoravel}%`} label="Resultados favoráveis ou acordos" color={chartColors.green} />
        <AnalyticsKpi icon={Target} value={String(data.total_analisados)} label="Processos concluídos analisados" color={chartColors.red} />
        <AnalyticsKpi icon={TrendingUp} value={String(data.processos_ativos)} label="Processos ativos na carteira" color={chartColors.yellow} />
      </section>

      <section className="grid jurimetria-charts" aria-label="Análises estatísticas">
        <article className="panel panel--padded chart-container">
          <div className="section-heading"><div><h2>Resultados por vara</h2><p>Percentual favorável e desfavorável</p></div></div>
          {data.por_vara.length ? (
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={data.por_vara} layout="vertical" margin={{ top: 4, right: 8, left: 5, bottom: 0 }}>
                <CartesianGrid strokeDasharray="4 4" stroke="#e4eff1" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} axisLine={false} tickLine={false} tick={{ fill: '#8da0a6', fontSize: 10 }} />
                <YAxis dataKey="vara" type="category" width={115} axisLine={false} tickLine={false} tick={{ fill: '#688088', fontSize: 10 }} />
                <Tooltip content={<ChartTooltip suffix="%" />} cursor={{ fill: '#f5fafb' }} />
                <Legend iconType="circle" iconSize={8} wrapperStyle={{ color: '#688088', fontSize: '11px', paddingTop: '12px' }} />
                <Bar dataKey="favoravel" name="Favorável/acordo" stackId="resultado" fill={chartColors.green} maxBarSize={22} />
                <Bar dataKey="desfavoravel" name="Desfavorável" stackId="resultado" fill={chartColors.red} radius={[0, 6, 6, 0]} maxBarSize={22} />
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="empty-state">Finalize processos e informe seus resultados para preencher este gráfico.</p>}
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

      <section className="panel ai-analysis">
        <span className="ai-analysis__icon"><Sparkles size={21} aria-hidden="true" /></span>
        <div><h2>Leitura da carteira</h2><p>{data.insight}</p></div>
      </section>
    </div>
  );
};

export default Jurimetria;
