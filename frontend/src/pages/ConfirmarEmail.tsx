import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import AuthShell from '../components/auth/AuthShell';
import Feedback from '../components/ui/Feedback';
import { useAuth } from '../contexts/auth';
import { contaService } from '../features/conta/api';
import { normalizeSessao } from '../features/escritorios/sessionAdapter';
import { authService } from '../services/juripredict';
import { getApiError } from '../services/api';

type Etapa = 'confirmando' | 'ok' | 'erro';

const ConfirmarEmail = () => {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const { user, updateUser } = useAuth();
  const [etapa, setEtapa] = useState<Etapa>(token ? 'confirmando' : 'erro');
  const [erro, setErro] = useState(token ? '' : 'Este link está incompleto.');

  useEffect(() => {
    if (!token) return;
    let ativo = true;
    contaService.confirmarEmail(token)
      .then(async () => {
        if (!ativo) return;
        setEtapa('ok');
        // Quem já está logado deixa de ver o aviso sem precisar entrar de novo.
        if (user) {
          try {
            updateUser(normalizeSessao(await authService.me(), user).usuario);
          } catch {
            // o aviso some no próximo carregamento da sessão
          }
        }
      })
      .catch((requestError) => {
        if (!ativo) return;
        setErro(getApiError(requestError));
        setEtapa('erro');
      });
    return () => { ativo = false; };
    // `user` fica de fora: só o token dispara a confirmação, uma vez.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  return (
    <AuthShell
      eyebrow="Confirmação de e-mail"
      title={etapa === 'ok' ? 'E-mail confirmado' : 'Confirmando seu e-mail'}
      description="Isso garante que você receba os avisos de prazos e audiências."
    >
      {etapa === 'confirmando' && <Feedback type="info">Confirmando...</Feedback>}
      {etapa === 'ok' && <Feedback type="success">Tudo certo. Seu e-mail foi confirmado.</Feedback>}
      {etapa === 'erro' && <Feedback type="error">{erro}</Feedback>}
      <p className="login-card__alt">
        <Link to={user ? '/' : '/login'}>{user ? 'Ir para o sistema' : 'Ir para o login'}</Link>
      </p>
    </AuthShell>
  );
};

export default ConfirmarEmail;
