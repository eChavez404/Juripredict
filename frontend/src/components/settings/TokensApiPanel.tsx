import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Bot, Copy, Plus } from 'lucide-react';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';
import { contaService } from '../../features/conta/api';
import type { TokenApi, TokenApiCriado } from '../../features/conta/types';
import { getApiError } from '../../services/api';

const formatar = (valor: string | null) => (
  valor ? new Intl.DateTimeFormat('pt-BR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(valor)) : 'nunca'
);

const situacao = (token: TokenApi) => {
  if (token.revogado_em) return 'Revogado';
  return token.ativo ? 'Ativo' : 'Expirado';
};

/** Credenciais somente leitura para agentes (MCP). O texto do token aparece uma única vez. */
const TokensApiPanel = () => {
  const [tokens, setTokens] = useState<TokenApi[]>([]);
  const [erro, setErro] = useState('');
  const [criarAberto, setCriarAberto] = useState(false);
  const [nome, setNome] = useState('');
  const [senha, setSenha] = useState('');
  const [validade, setValidade] = useState('90');
  const [busy, setBusy] = useState(false);
  const [erroCriar, setErroCriar] = useState('');
  const [criado, setCriado] = useState<TokenApiCriado | null>(null);
  const [copiado, setCopiado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setTokens(await contaService.listarTokens());
    } catch (requestError) {
      setErro(getApiError(requestError));
    }
  }, []);

  useEffect(() => { void carregar(); }, [carregar]);

  const fecharCriacao = () => {
    if (busy) return;
    setCriarAberto(false);
    setNome('');
    setSenha('');
    setValidade('90');
    setErroCriar('');
  };

  const criar = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErroCriar('');
    try {
      const resposta = await contaService.criarToken({ nome, senha, validade_dias: Number(validade) });
      setCriado(resposta);
      setCriarAberto(false);
      setNome('');
      setSenha('');
      await carregar();
    } catch (requestError) {
      setErroCriar(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  const revogar = async (token: TokenApi) => {
    setErro('');
    try {
      await contaService.revogarToken(token.id);
      await carregar();
    } catch (requestError) {
      setErro(getApiError(requestError));
    }
  };

  const copiar = async () => {
    if (!criado) return;
    try {
      await navigator.clipboard.writeText(criado.token);
      setCopiado(true);
    } catch {
      setCopiado(false); // sem permissão de área de transferência: a pessoa copia à mão
    }
  };

  const fecharToken = () => {
    setCriado(null);
    setCopiado(false);
  };

  return (
    <article className="panel panel--padded settings-card">
      <div className="section-heading">
        <div>
          <h2><Bot size={18} /> Acesso por agentes</h2>
          <p>Tokens somente leitura para conectar um agente (MCP) ao seu escritório</p>
        </div>
      </div>

      {erro && <Feedback type="error">{erro}</Feedback>}

      <div className="entity-form">
        <p className="confirm-copy">
          Um token deixa um agente consultar processos, andamentos, agenda e indicadores. Ele não
          altera nada, não acessa clientes e cada consulta fica registrada na auditoria. Trocar a
          senha ou excluir a conta revoga todos.
        </p>

        {tokens.length === 0 ? (
          <p className="andamentos__vazio">Nenhum token criado.</p>
        ) : (
          <ul className="documentos__lista">
            {tokens.map((token) => (
              <li key={token.id}>
                <Bot size={16} aria-hidden="true" />
                <span>{token.nome} <small>({token.prefixo}…)</small></span>
                <small>
                  {situacao(token)} · expira {formatar(token.expira_em)} · último uso {formatar(token.ultimo_uso_em)}
                </small>
                {token.ativo && (
                  <button
                    className="button button--secondary button--small"
                    type="button"
                    onClick={() => void revogar(token)}
                    aria-label={`Revogar token ${token.nome}`}
                  >
                    Revogar
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        <div className="form-actions">
          <button className="button button--secondary" type="button" onClick={() => setCriarAberto(true)}>
            <Plus size={16} /> Criar token
          </button>
        </div>
      </div>

      <Modal open={criarAberto} title="Criar token de API" description="Confirme com a sua senha." onClose={fecharCriacao}>
        <form onSubmit={criar}>
          {erroCriar && <Feedback type="error">{erroCriar}</Feedback>}
          <label className="form-field form-field--full">
            Nome (para reconhecer depois)
            <input className="input" value={nome} onChange={(event) => setNome(event.target.value)} maxLength={80} required />
          </label>
          <label className="form-field form-field--full">
            Validade
            <select className="input" value={validade} onChange={(event) => setValidade(event.target.value)}>
              <option value="30">30 dias</option>
              <option value="90">90 dias</option>
              <option value="180">180 dias</option>
              <option value="365">365 dias</option>
            </select>
          </label>
          <label className="form-field form-field--full">
            Senha
            <input
              className="input"
              type="password"
              autoComplete="current-password"
              value={senha}
              onChange={(event) => setSenha(event.target.value)}
              required
            />
          </label>
          <div className="form-actions">
            <button className="button button--secondary" type="button" onClick={fecharCriacao} disabled={busy}>Cancelar</button>
            <button className="button button--primary" type="submit" disabled={busy}>
              {busy ? 'Criando...' : 'Criar token'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(criado)} title="Token criado" description="Copie agora: ele não será mostrado de novo." onClose={fecharToken}>
        <p className="confirm-copy">
          Guarde o token como uma senha. Quem o tiver lê os dados do seu escritório até ele expirar ou
          ser revogado.
        </p>
        <code className="token-api__texto" data-testid="token-criado">{criado?.token}</code>
        <div className="form-actions">
          <button className="button button--secondary" type="button" onClick={() => void copiar()}>
            <Copy size={16} /> {copiado ? 'Copiado' : 'Copiar'}
          </button>
          <button className="button button--primary" type="button" onClick={fecharToken}>Já guardei</button>
        </div>
      </Modal>
    </article>
  );
};

export default TokensApiPanel;
