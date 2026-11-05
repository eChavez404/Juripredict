import type { InputHTMLAttributes } from 'react';
import type { LucideIcon } from 'lucide-react';

type AuthFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  id: string;
  label: string;
  icon: LucideIcon;
  hint?: string;
};

/** Campo com rótulo e ícone, no mesmo desenho do formulário de login. */
const AuthField = ({ id, label, icon: Icon, hint, ...input }: AuthFieldProps) => (
  <div>
    <label className="field-label" htmlFor={id}>{label}</label>
    <div className="input-wrap">
      <Icon size={17} aria-hidden="true" />
      <input className="input" id={id} aria-describedby={hint ? `${id}-hint` : undefined} {...input} />
    </div>
    {hint && <p className="field-hint" id={`${id}-hint`}>{hint}</p>}
  </div>
);

export default AuthField;
