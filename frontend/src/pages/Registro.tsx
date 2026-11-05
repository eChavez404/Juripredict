import { useState, type ChangeEvent, type FormEvent } from 'react';
import { ArrowRight, Building2, Lock, Mail, User } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import AuthField from '../components/auth/AuthField';
import AuthShell from '../components/auth/AuthShell';
import Feedback from '../components/ui/Feedback';
import { useAuth } from '../contexts/auth';
import { contaService } from '../features/conta/api';
import { getApiError } from '../services/api';

type Campos = { nome: string; escritorio_nome: string; email: string; senha: string };

const Registro = () => {
  const [form, setForm] = useState<Campos>({ nome: '', escritorio_nome: '', email: '', senha: '' });
  const [aceite, setAceite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const { startSession } = useAuth();
  const navigate = useNavigate();

  const campo = (name: keyof Campos) => ({
    value: form[name],
    onChange: (event: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [name]: event.target.value }),
    required: true,
  });

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await startSession(await contaService.registrar({ ...form, aceite_termos: aceite }));
      navigate('/');
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Novo escritório"
      title="Crie sua conta"
      description="Você será o proprietário do escritório e poderá convidar sua equipe depois."
    >
      {error && <Feedback type="error">{error}</Feedback>}

      <form className="login-form" onSubmit={handleSubmit}>
        <AuthField id="nome" label="Seu nome" icon={User} autoComplete="name" maxLength={150} {...campo('nome')} />
        <AuthField
          id="escritorio"
          label="Nome do escritório"
          icon={Building2}
          autoComplete="organization"
          maxLength={255}
          {...campo('escritorio_nome')}
        />
        <AuthField
          id="email"
          label="E-mail profissional"
          icon={Mail}
          type="email"
          autoComplete="email"
          maxLength={150}
          {...campo('email')}
        />
        <AuthField
          id="senha"
          label="Senha"
          icon={Lock}
          type="password"
          autoComplete="new-password"
          minLength={8}
          hint="Mínimo de 8 caracteres, sem ser uma senha comum ou só números."
          {...campo('senha')}
        />

        <label className="checkbox-label">
          <input type="checkbox" checked={aceite} onChange={(event) => setAceite(event.target.checked)} required />
          <span>
            Li e aceito os <Link to="/termos" target="_blank">Termos de Uso</Link> e a{' '}
            <Link to="/privacidade" target="_blank">Política de Privacidade</Link>.
          </span>
        </label>

        <button className="button button--primary" type="submit" disabled={busy}>
          {busy ? 'Criando conta...' : 'Criar conta'} <ArrowRight size={17} />
        </button>
      </form>

      <p className="login-card__alt">Já tem conta? <Link to="/login">Entrar</Link></p>
    </AuthShell>
  );
};

export default Registro;
