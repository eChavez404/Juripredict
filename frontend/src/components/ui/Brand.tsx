import { Scale } from 'lucide-react';

type BrandProps = {
  compact?: boolean;
  inverse?: boolean;
};

const Brand = ({ compact = false, inverse = false }: BrandProps) => (
  <div className={`brand${inverse ? ' brand--inverse' : ''}`}>
    <span className="brand__mark" aria-hidden="true">
      <Scale size={compact ? 20 : 24} strokeWidth={2.2} />
    </span>
    <span className="brand__text">
      <strong>Juri<span>Predict</span></strong>
      {!compact && <small>Inteligência jurídica</small>}
    </span>
  </div>
);

export default Brand;
