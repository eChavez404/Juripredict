import { useState, type FormEvent } from 'react';
import { ArrowRight, Lock, Mail } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import AuthField from '../components/auth/AuthField';
import AuthShell from '../components/auth/AuthShell';
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
    <AuthShell
      eyebrow="Área segura"
      title="Bem-vindo de volta"
      description="Acesse sua conta para continuar acompanhando o escritório."
    >
      {error && <Feedback type="error">{error}</Feedback>}

      <form className="login-form" onSubmit={handleLogin}>
        <AuthField
          id="email"
          label="E-mail profissional"
          icon={Mail}
          type="email"
          autoComplete="email"
          placeholder="advogado@gmail.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <AuthField
          id="password"
          label="Senha"
          icon={Lock}
          type="password"
          autoComplete="current-password"
          placeholder="Digite sua senha"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          required
        />

        <div className="login-form__options">
          <span />
          <Link to="/esqueci-senha">Esqueceu a senha?</Link>
        </div>

        <button className="button button--primary" type="submit" disabled={busy}>
          {busy ? 'Entrando...' : 'Acessar plataforma'} <ArrowRight size={17} />
        </button>
      </form>

      <p className="login-card__alt">
        Ainda não tem conta? <Link to="/registro">Criar conta do escritório</Link>
      </p>
    </AuthShell>
  );
};

export default Login;
