import { useState } from 'react';
import { useAuth } from '../../contexts/auth';
import { contaService } from '../../features/conta/api';
import { getApiError } from '../../services/api';

/** Aviso fixo até a pessoa confirmar o e-mail. Não bloqueia o uso do sistema. */
const EmailVerificationBanner = () => {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [failed, setFailed] = useState(false);

  // `undefined` = sessão antiga, gravada antes do campo existir: não incomoda.
  if (user?.email_verificado !== false) return null;

  const reenviar = async () => {
    setBusy(true);
    setMessage('');
    setFailed(false);
    try {
      await contaService.reenviarVerificacao();
      setMessage('Enviamos um novo link para o seu e-mail.');
    } catch (requestError) {
      setFailed(true);
      setMessage(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="email-banner" role="status">
      <span>
        Confirme seu e-mail ({user.email}) pelo link que enviamos ao criar a conta.
      </span>
      <button className="button button--secondary button--small" type="button" onClick={reenviar} disabled={busy}>
        {busy ? 'Enviando...' : 'Reenviar link'}
      </button>
      {message && (
        <span className={failed ? 'email-banner__erro' : 'email-banner__ok'} role={failed ? 'alert' : undefined}>
          {message}
        </span>
      )}
    </div>
  );
};

export default EmailVerificationBanner;
