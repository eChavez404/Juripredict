import { useState, type FormEvent } from 'react';
import { ArrowRight, Lock } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import AuthField from '../components/auth/AuthField';
import AuthShell from '../components/auth/AuthShell';
import Feedback from '../components/ui/Feedback';
import { contaService } from '../features/conta/api';
import { getApiError } from '../services/api';

const RedefinirSenha = () => {
  const [params] = useSearchParams();
  const uid = params.get('uid') ?? '';
  const token = params.get('token') ?? '';
  const [senha, setSenha] = useState('');
  const [confirmacao, setConfirmacao] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [concluido, setConcluido] = useState(false);

  const linkIncompleto = !uid || !token;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (senha !== confirmacao) {
      setError('As senhas não coincidem.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await contaService.confirmarReset({ uid, token, nova_senha: senha });
      setConcluido(true);
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Recuperar acesso"
      title="Crie uma nova senha"
      description="Escolha uma senha que você não use em outros serviços."
    >
      {linkIncompleto && (
        <Feedback type="error">Este link está incompleto. Solicite um novo para continuar.</Feedback>
      )}
      {error && <Feedback type="error">{error}</Feedback>}

      {concluido && <Feedback type="success">Senha redefinida com sucesso. Você já pode entrar.</Feedback>}

      {!concluido && !linkIncompleto && (
        <form className="login-form" onSubmit={handleSubmit}>
          <AuthField
            id="nova-senha"
            label="Nova senha"
            icon={Lock}
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={senha}
            onChange={(event) => setSenha(event.target.value)}
            required
          />
          <AuthField
            id="confirmar-senha"
            label="Confirmar nova senha"
            icon={Lock}
            type="password"
            autoComplete="new-password"
            minLength={8}
            value={confirmacao}
            onChange={(event) => setConfirmacao(event.target.value)}
            required
          />
          <button className="button button--primary" type="submit" disabled={busy}>
            {busy ? 'Salvando...' : 'Redefinir senha'} <ArrowRight size={17} />
          </button>
        </form>
      )}

      <p className="login-card__alt">
        {linkIncompleto
          ? <Link to="/esqueci-senha">Solicitar novo link</Link>
          : <Link to="/login">Ir para o login</Link>}
      </p>
    </AuthShell>
  );
};

export default RedefinirSenha;
