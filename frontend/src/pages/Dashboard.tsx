import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, ArrowRight, CalendarClock, Scale, Sparkles, TrendingUp, Users } from 'lucide-react';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import ChartTooltip from '../components/ui/ChartTooltip';
import Feedback from '../components/ui/Feedback';
import MetricCard from '../components/ui/MetricCard';
import PageHeader from '../components/ui/PageHeader';
import { useAuth } from '../contexts/auth';
import { getApiError } from '../services/api';
import { dashboardService, jurimetriaService } from '../services/juripredict';
import type { DashboardData, JurimetriaData } from '../types';

const chartColors = { green: '#72a888', yellow: '#d2aa61', red: '#c87979' };
const statusColors = [chartColors.green, chartColors.yellow, chartColors.red];

const Dashboard = () => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [analytics, setAnalytics] = useState<JurimetriaData | null>(null);
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const { user } = useAuth();

  useEffect(() => {
    Promise.all([dashboardService.get(), jurimetriaService.get()])
      .then(([dashboard, jurimetria]) => {
        setData(dashboard);
        setAnalytics(jurimetria);
      })
      .catch((requestError) => setError(getApiError(requestError)));
  }, []);

  if (error) return <div className="page"><Feedback type="error">{error}</Feedback></div>;
  if (!data) return <div className="page"><div className="panel empty-state">Carregando indicadores...</div></div>;

  return (
    <div className="page">
      <PageHeader eyebrow="Visão geral" title={`Olá, ${user?.nome || user?.username || 'Advogado'}`} description="Indicadores atualizados com os dados reais do seu escritório." />

      <section className="grid metrics-grid" aria-label="Indicadores principais">
        <MetricCard label="Processos ativos" value={String(data.metricas.processos_ativos)} icon={Scale} detail="na carteira" tone="cyan" />
        <MetricCard label="Novos clientes" value={String(data.metricas.novos_clientes_mes)} icon={Users} detail="neste mês" tone="green" />
        <MetricCard label="Prazos na semana" value={String(data.metricas.prazos_semana)} icon={CalendarClock} detail="pendentes" tone="yellow" />
        <MetricCard label="Audiências próximas" value={String(data.metricas.audiencias_proximas)} icon={AlertCircle} detail="agendadas" tone="red" />
      </section>

      <section className="grid dashboard-charts" aria-label="Indicadores em gráficos">
        <article className="panel panel--padded chart-container">
          <div className="section-heading"><div><h2>Evolução dos processos</h2><p>Movimentação nos últimos seis meses</p></div></div>
          <ResponsiveContainer width="100%" height={270}>
            <AreaChart data={data.evolucao_processos} margin={{ top: 8, right: 6, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="ativosGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={chartColors.green} stopOpacity={0.28} /><stop offset="95%" stopColor={chartColors.green} stopOpacity={0.02} /></linearGradient>
                <linearGradient id="novosGradient" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor={chartColors.yellow} stopOpacity={0.25} /><stop offset="95%" stopColor={chartColors.yellow} stopOpacity={0.02} /></linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="4 4" stroke="#e4eff1" vertical={false} />
              <XAxis dataKey="mes" axisLine={false} tickLine={false} tick={{ fill: '#8da0a6', fontSize: 11 }} dy={8} />
              <YAxis axisLine={false} tickLine={false} allowDecimals={false} tick={{ fill: '#8da0a6', fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />} />
              <Area type="monotone" dataKey="ativos" name="Ativos" stroke={chartColors.green} strokeWidth={2} fill="url(#ativosGradient)" />
              <Area type="monotone" dataKey="novos" name="Novos" stroke={chartColors.yellow} strokeWidth={2} fill="url(#novosGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        </article>

        <article className="panel panel--padded chart-container">
          <div className="section-heading"><div><h2>Status dos processos</h2><p>Distribuição da carteira atual</p></div></div>
          <ResponsiveContainer width="100%" height={205}>
            <PieChart><Pie data={data.status_processos} dataKey="value" cx="50%" cy="50%" innerRadius={52} outerRadius={78} paddingAngle={5} stroke="none">{data.status_processos.map((item, index) => <Cell key={item.name} fill={statusColors[index]} />)}</Pie><Tooltip content={<ChartTooltip />} /></PieChart>
          </ResponsiveContainer>
          <div className="chart-legend">{data.status_processos.map((item, index) => <span className="chart-legend__item" key={item.name}><i className="chart-legend__dot" style={{ backgroundColor: statusColors[index] }} />{item.name} · {item.value}</span>)}</div>
        </article>
      </section>

      <section className="grid dashboard-bottom">
        <article className="panel panel--padded chart-container">
          <div className="section-heading"><div><h2>Prazos da semana</h2><p>Distribuição por dia útil</p></div></div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.prazos_semana} margin={{ top: 5, right: 4, left: -28, bottom: 0 }}><CartesianGrid strokeDasharray="4 4" stroke="#e4eff1" vertical={false} /><XAxis dataKey="dia" axisLine={false} tickLine={false} tick={{ fill: '#8da0a6', fontSize: 11 }} dy={8} /><YAxis axisLine={false} tickLine={false} allowDecimals={false} tick={{ fill: '#8da0a6', fontSize: 11 }} /><Tooltip content={<ChartTooltip />} cursor={{ fill: '#f3f8f9' }} /><Bar dataKey="qtd" name="Prazos" fill={chartColors.yellow} radius={[7, 7, 2, 2]} maxBarSize={32} /></BarChart>
          </ResponsiveContainer>
        </article>

        <article className="panel panel--padded">
          <div className="section-heading"><div><h2>Processos recentes</h2><p>Últimas atualizações</p></div><button className="button button--secondary button--small" type="button" onClick={() => navigate('/processos')}>Ver todos <ArrowRight size={13} /></button></div>
          <div className="recent-list">
            {data.processos_recentes.map((processo) => <div className="recent-item" key={processo.id}><div className="recent-item__topline"><strong>{processo.numero_cnj}</strong><span className="status-badge status-badge--cyan">{processo.status}</span></div><p>{processo.cliente_nome} · {processo.vara}</p></div>)}
            {data.processos_recentes.length === 0 && <p className="empty-state">Nenhum processo cadastrado.</p>}
          </div>
        </article>

        <article className="panel panel--padded panel--accent insight-card">
          <div className="section-heading"><div><h2 className="insight-card__title"><Sparkles size={18} /> Resumo jurimétrico</h2><p>Calculado com a sua carteira</p></div></div>
          <p className="insight-card__copy">{analytics?.insight ?? 'Cadastre resultados nos processos para gerar análises.'}</p>
          <div className="recommendation"><strong>Base analisada</strong>{analytics?.total_analisados ?? 0} processos concluídos · {analytics?.taxa_favoravel ?? 0}% favoráveis ou acordos.</div>
          <button className="button button--primary" type="button" onClick={() => navigate('/jurimetria')}><TrendingUp size={16} /> Abrir análise completa</button>
        </article>
      </section>
    </div>
  );
};

export default Dashboard;
