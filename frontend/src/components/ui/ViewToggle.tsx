import { LayoutGrid, TableProperties } from 'lucide-react';

export type CollectionView = 'table' | 'cards';

type ViewToggleProps = {
  value: CollectionView;
  onChange: (view: CollectionView) => void;
  label?: string;
};

const ViewToggle = ({ value, onChange, label = 'Modo de visualização' }: ViewToggleProps) => (
  <div className="view-toggle" role="group" aria-label={label}>
    <button
      className={value === 'table' ? 'view-toggle__button view-toggle__button--active' : 'view-toggle__button'}
      type="button"
      aria-pressed={value === 'table'}
      onClick={() => onChange('table')}
    >
      <TableProperties size={15} aria-hidden="true" />
      <span>Tabela</span>
    </button>
    <button
      className={value === 'cards' ? 'view-toggle__button view-toggle__button--active' : 'view-toggle__button'}
      type="button"
      aria-pressed={value === 'cards'}
      onClick={() => onChange('cards')}
    >
      <LayoutGrid size={15} aria-hidden="true" />
      <span>Cards</span>
    </button>
  </div>
);

export default ViewToggle;
