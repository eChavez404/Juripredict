import { useState, type FormEvent } from 'react';
import { ArrowRight, Lock, User } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import AuthField from '../components/auth/AuthField';
import AuthShell from '../components/auth/AuthShell';
import Feedback from '../components/ui/Feedback';
import { useAuth } from '../contexts/auth';
import { contaService } from '../features/conta/api';
import { getApiError } from '../services/api';

const AceitarConvite = () => {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const [contaExistente, setContaExistente] = useState(false);
  const [nome, setNome] = useState('');
  const [senha, setSenha] = useState('');
  const [aceite, setAceite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const { startSession } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const sessao = await contaService.aceitarConvite(
        contaExistente
          ? { token, senha }
          : { token, senha, nome, aceite_termos: aceite },
      );
      await startSession(sessao);
      navigate('/');
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Convite"
      title="Entrar no escritório"
      description="Você foi convidado para participar de um escritório no JuriPredict."
    >
      {!token && <Feedback type="error">Este link de convite está incompleto.</Feedback>}
      {error && <Feedback type="error">{error}</Feedback>}

      {token && (
        <form className="login-form" onSubmit={handleSubmit}>
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={contaExistente}
              onChange={(event) => setContaExistente(event.target.checked)}
            />
            <span>Já tenho conta no JuriPredict</span>
          </label>

          {!contaExistente && (
            <AuthField
              id="nome"
              label="Seu nome"
              icon={User}
              autoComplete="name"
              maxLength={150}
              value={nome}
              onChange={(event) => setNome(event.target.value)}
              required
            />
          )}

          <AuthField
            id="senha"
            label={contaExistente ? 'Senha da sua conta' : 'Crie uma senha'}
            icon={Lock}
            type="password"
            autoComplete={contaExistente ? 'current-password' : 'new-password'}
            minLength={contaExistente ? undefined : 8}
            hint={contaExistente ? 'Confirmamos que a conta é sua pela senha atual.' : 'Mínimo de 8 caracteres.'}
            value={senha}
            onChange={(event) => setSenha(event.target.value)}
            required
          />

          {!contaExistente && (
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={aceite}
                onChange={(event) => setAceite(event.target.checked)}
                required
              />
              <span>
                Li e aceito os <Link to="/termos" target="_blank">Termos de Uso</Link> e a{' '}
                <Link to="/privacidade" target="_blank">Política de Privacidade</Link>.
              </span>
            </label>
          )}

          <button className="button button--primary" type="submit" disabled={busy}>
            {busy ? 'Entrando...' : 'Aceitar convite'} <ArrowRight size={17} />
          </button>
        </form>
      )}

      <p className="login-card__alt"><Link to="/login">Voltar para o login</Link></p>
    </AuthShell>
  );
};

export default AceitarConvite;
