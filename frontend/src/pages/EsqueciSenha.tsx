import { useState, type FormEvent } from 'react';
import { ArrowRight, Mail } from 'lucide-react';
import { Link } from 'react-router-dom';
import AuthField from '../components/auth/AuthField';
import AuthShell from '../components/auth/AuthShell';
import Feedback from '../components/ui/Feedback';
import { contaService } from '../features/conta/api';
import { getApiError } from '../services/api';

const EsqueciSenha = () => {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [enviado, setEnviado] = useState(false);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await contaService.solicitarReset(email);
      setEnviado(true);
    } catch (requestError) {
      setError(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Recuperar acesso"
      title="Esqueceu a senha?"
      description="Informe o e-mail da sua conta e enviaremos um link para criar uma nova senha."
    >
      {error && <Feedback type="error">{error}</Feedback>}
      {enviado ? (
        <Feedback type="success">
          Se o e-mail estiver cadastrado, você receberá as instruções em alguns minutos. Confira também a caixa de spam.
        </Feedback>
      ) : (
        <form className="login-form" onSubmit={handleSubmit}>
          <AuthField
            id="email"
            label="E-mail da conta"
            icon={Mail}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <button className="button button--primary" type="submit" disabled={busy}>
            {busy ? 'Enviando...' : 'Enviar link'} <ArrowRight size={17} />
          </button>
        </form>
      )}

      <p className="login-card__alt"><Link to="/login">Voltar para o login</Link></p>
    </AuthShell>
  );
};

export default EsqueciSenha;
