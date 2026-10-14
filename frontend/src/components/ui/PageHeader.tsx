import type { ReactNode } from 'react';
import { ArrowLeft } from 'lucide-react';
import { useNavigate, type To } from 'react-router-dom';

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
  backTo?: To;
  backLabel?: string;
};

const PageHeader = ({
  eyebrow,
  title,
  description,
  action,
  backTo,
  backLabel = 'Voltar',
}: PageHeaderProps) => {
  const navigate = useNavigate();

  return (
    <header className="page-header">
      <div className="page-header__copy">
        {backTo && (
          <button className="back-button" type="button" onClick={() => navigate(backTo)}>
            <ArrowLeft size={16} aria-hidden="true" />
            {backLabel}
          </button>
        )}
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action && <div className="page-header__action">{action}</div>}
    </header>
  );
};

export default PageHeader;
