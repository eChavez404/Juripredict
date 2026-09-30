import { Search } from 'lucide-react';

type SearchFieldProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  label?: string;
};

const SearchField = ({ value, onChange, placeholder, label = 'Buscar' }: SearchFieldProps) => (
  <label className="search-field">
    <span className="sr-only">{label}</span>
    <Search size={18} aria-hidden="true" />
    <input
      type="search"
      value={value}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
    />
  </label>
);

export default SearchField;
