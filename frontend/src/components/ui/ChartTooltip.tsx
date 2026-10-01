type TooltipPayload = {
  color?: string;
  fill?: string;
  name?: string;
  value?: number | string;
};

type ChartTooltipProps = {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
  suffix?: string;
};

const ChartTooltip = ({ active, payload, label, suffix = '' }: ChartTooltipProps) => {
  if (!active || !payload?.length) return null;

  return (
    <div className="chart-tooltip">
      {label && <p className="chart-tooltip__label">{label}</p>}
      {payload.map((item, index) => (
        <p key={`${item.name}-${index}`} style={{ color: item.color ?? item.fill }}>
          {item.name}: <strong>{item.value}{suffix}</strong>
        </p>
      ))}
    </div>
  );
};

export default ChartTooltip;
