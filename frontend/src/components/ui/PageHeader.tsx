import type { ReactNode } from 'react';

type PageHeaderProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: ReactNode;
};

const PageHeader = ({ eyebrow, title, description, action }: PageHeaderProps) => (
  <header className="page-header">
    <div>
      {eyebrow && <span className="eyebrow">{eyebrow}</span>}
      <h1>{title}</h1>
      {description && <p>{description}</p>}
    </div>
    {action && <div className="page-header__action">{action}</div>}
  </header>
);

export default PageHeader;
