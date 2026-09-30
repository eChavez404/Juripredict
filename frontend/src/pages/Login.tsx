import { useState, type FormEvent } from 'react';
import { ArrowRight, Lock, Mail, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Brand from '../components/ui/Brand';
import Feedback from '../components/ui/Feedback';
import { useAuth } from '../contexts/auth';
import { getApiError } from '../services/api';

const Login = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleLogin = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await login(email, password);
      navigate('/');
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
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
            <span className="eyebrow">Área segura</span>
            <h2>Bem-vindo de volta</h2>
            <p>Acesse sua conta para continuar acompanhando o escritório.</p>
          </header>

          {error && <Feedback type="error">{error}</Feedback>}

          <form className="login-form" onSubmit={handleLogin}>
            <div>
              <label className="field-label" htmlFor="email">E-mail profissional</label>
              <div className="input-wrap">
                <Mail size={17} aria-hidden="true" />
                <input
                  className="input"
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="advogado@gmail.com"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </div>
            </div>

            <div>
              <label className="field-label" htmlFor="password">Senha</label>
              <div className="input-wrap">
                <Lock size={17} aria-hidden="true" />
                <input
                  className="input"
                  id="password"
                  type="password"
                  autoComplete="current-password"
                  placeholder="Digite sua senha"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
              </div>
            </div>

            <div className="login-form__options">
              <label className="checkbox-label">
                <input type="checkbox" />
                Lembrar meu acesso
              </label>
              <button className="text-button" type="button">Esqueceu a senha?</button>
            </div>

            <button className="button button--primary" type="submit" disabled={busy}>
              {busy ? 'Entrando...' : 'Acessar plataforma'} <ArrowRight size={17} />
            </button>
          </form>

          <p className="login-card__security">
            <ShieldCheck size={14} aria-hidden="true" />
            Seus dados são protegidos e criptografados.
          </p>
        </div>
      </section>
    </main>
  );
};

export default Login;
