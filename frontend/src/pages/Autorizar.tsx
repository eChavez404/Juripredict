import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Check, X } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import AuthShell from '../components/auth/AuthShell';
import Feedback from '../components/ui/Feedback';
import { contaService } from '../features/conta/api';
import type { PedidoOAuth } from '../features/conta/types';
import { getApiError } from '../services/api';

// Parâmetros do pedido OAuth que voltam ao servidor sem alteração.
const CAMPOS = [
  'client_id', 'redirect_uri', 'response_type', 'code_challenge',
  'code_challenge_method', 'state', 'resource', 'scope',
];

const PERMISSOES = [
  'Ler processos, andamentos e a lista de documentos, sem abrir os arquivos',
  'Ler a agenda, os prazos e as pendências',
  'Ler a jurimetria da carteira, conforme o seu papel no escritório',
];

const navegar = (url: string) => window.location.assign(url);

/** Erro que o servidor manda devolver ao aplicativo, pela URL que ele registrou. */
const retornoDoErro = (error: unknown): string | null => {
  const dados: unknown = axios.isAxiosError(error) ? error.response?.data : null;
  const url = dados && typeof dados === 'object' ? (dados as { redirecionar?: unknown }).redirecionar : null;
  return typeof url === 'string' ? url : null;
};

/** Consentimento do conector MCP remoto (OAuth): um aplicativo pede para ler um escritório. */
const Autorizar = ({ irPara = navegar }: { irPara?: (url: string) => void }) => {
  const [searchParams] = useSearchParams();
  const params = useMemo(
    () => Object.fromEntries(CAMPOS.flatMap((campo) => {
      const valor = searchParams.get(campo);
      return valor === null ? [] : [[campo, valor]];
    })),
    [searchParams],
  );
  const [pedido, setPedido] = useState<PedidoOAuth | null>(null);
  const [escritorio, setEscritorio] = useState('');
  const [erro, setErro] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let ativo = true;
    contaService.pedidoOAuth(params)
      .then((dados) => {
        if (!ativo) return;
        setPedido(dados);
        setEscritorio(dados.escritorios[0]?.id ?? '');
      })
      .catch((error: unknown) => {
        if (!ativo) return;
        const url = retornoDoErro(error);
        if (url) irPara(url);
        else setErro(getApiError(error));
      });
    return () => { ativo = false; };
  }, [params, irPara]);

  const decidir = async (permitir: boolean) => {
    setBusy(true);
    setErro('');
    try {
      const { redirecionar } = await contaService.decidirOAuth({ ...params, permitir, escritorio_id: escritorio });
      irPara(redirecionar); // segue ocupado: o navegador está saindo da página
    } catch (error) {
      const url = retornoDoErro(error);
      if (url) {
        irPara(url);
        return;
      }
      setErro(getApiError(error));
      setBusy(false);
    }
  };

  return (
    <AuthShell
      eyebrow="Conectar aplicativo"
      title={pedido ? `${pedido.aplicativo} quer acessar o JuriPredict` : 'Conectar aplicativo'}
      description="O acesso é somente leitura e vale para um escritório. Cada consulta fica na auditoria, e você pode revogá-lo quando quiser em Configurações."
    >
      {erro && <Feedback type="error">{erro}</Feedback>}
      {!pedido && !erro && <div className="route-loader" role="status" aria-label="Carregando" />}

      {pedido && (
        <div className="login-form">
          <ul className="consentimento__lista">
            {PERMISSOES.map((permissao) => (
              <li key={permissao}><Check size={16} aria-hidden="true" /> {permissao}</li>
            ))}
            <li className="consentimento__nunca"><X size={16} aria-hidden="true" /> Nunca cria, altera ou apaga nada</li>
          </ul>

          {pedido.escritorios.length === 0 && (
            <Feedback type="error">Sua conta não participa de nenhum escritório ativo.</Feedback>
          )}
          {pedido.escritorios.length === 1 && (
            <p className="confirm-copy">Escritório: <strong>{pedido.escritorios[0].nome}</strong></p>
          )}
          {pedido.escritorios.length > 1 && (
            <label className="form-field form-field--full">
              Escritório
              <select className="input" value={escritorio} onChange={(event) => setEscritorio(event.target.value)}>
                {pedido.escritorios.map((item) => <option key={item.id} value={item.id}>{item.nome}</option>)}
              </select>
            </label>
          )}

          <p className="confirm-copy">
            Ao responder, você volta para <strong>{pedido.destino}</strong>. Só permita se reconhecer
            esse endereço.
          </p>

          <div className="form-actions">
            <button className="button button--secondary" type="button" onClick={() => void decidir(false)} disabled={busy}>
              Negar
            </button>
            <button
              className="button button--primary"
              type="button"
              onClick={() => void decidir(true)}
              disabled={busy || !escritorio}
            >
              {busy ? 'Redirecionando...' : 'Permitir acesso'}
            </button>
          </div>
        </div>
      )}
    </AuthShell>
  );
};

export default Autorizar;
