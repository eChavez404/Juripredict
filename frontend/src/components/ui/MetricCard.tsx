import type { ElementType } from 'react';

type MetricTone = 'cyan' | 'green' | 'yellow' | 'red';

type MetricCardProps = {
  label: string;
  value: string;
  icon: ElementType;
  detail?: string;
  tone?: MetricTone;
};

const MetricCard = ({ label, value, icon: Icon, detail, tone = 'cyan' }: MetricCardProps) => (
  <article className={`metric-card metric-card--${tone}`}>
    <div className="metric-card__topline">
      <span className="metric-card__label">{label}</span>
      <span className="metric-card__icon" aria-hidden="true"><Icon size={20} /></span>
    </div>
    <div className="metric-card__value-row">
      <strong>{value}</strong>
      {detail && <span>{detail}</span>}
    </div>
  </article>
);

export default MetricCard;
