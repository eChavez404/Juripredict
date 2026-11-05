import type { ReactNode } from 'react';
import { ShieldCheck } from 'lucide-react';
import Brand from '../ui/Brand';

type AuthShellProps = {
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
};

/** Casca compartilhada pelas telas públicas: vitrine à esquerda, cartão à direita. */
const AuthShell = ({ eyebrow, title, description, children }: AuthShellProps) => (
  <main className="login-page">
    <section className="login-showcase" aria-label="Sobre a JuriPredict">
      <Brand inverse />

      <div className="login-showcase__content">
        <span>Decisões orientadas por dados</span>
        <h1>A advocacia mais clara, estratégica e previsível.</h1>
        <p>
          Centralize sua operação jurídica e transforme dados processuais em decisões
          mais seguras para o seu escritório.
        </p>
      </div>

      <p className="login-showcase__footer">Gestão jurídica e jurimetria em um só lugar.</p>
    </section>

    <section className="login-form-side">
      <div className="login-card">
        <div className="login-card__mobile-brand"><Brand /></div>
        <header className="login-card__header">
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
          <p>{description}</p>
        </header>

        {children}

        <p className="login-card__security">
          <ShieldCheck size={14} aria-hidden="true" />
          Seus dados são protegidos e criptografados.
        </p>
      </div>
    </section>
  </main>
);

export default AuthShell;
