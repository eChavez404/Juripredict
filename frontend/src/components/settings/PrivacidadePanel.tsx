import { useState, type FormEvent } from 'react';
import { Download, ShieldAlert, Trash2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';
import { useAuth } from '../../contexts/auth';
import { contaService } from '../../features/conta/api';
import { getApiError } from '../../services/api';

/** Direitos do titular: baixar os próprios dados e excluir a conta (LGPD, art. 18). */
const PrivacidadePanel = () => {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [baixando, setBaixando] = useState(false);
  const [erro, setErro] = useState('');
  const [excluirAberto, setExcluirAberto] = useState(false);
  const [senha, setSenha] = useState('');
  const [excluindo, setExcluindo] = useState(false);
  const [erroExclusao, setErroExclusao] = useState('');

  const baixar = async () => {
    setBaixando(true);
    setErro('');
    try {
      const arquivo = await contaService.exportarDados();
      const url = URL.createObjectURL(arquivo);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'meus-dados-juripredict.json';
      link.click();
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setErro(getApiError(requestError));
    } finally {
      setBaixando(false);
    }
  };

  const excluir = async (event: FormEvent) => {
    event.preventDefault();
    setExcluindo(true);
    setErroExclusao('');
    try {
      await contaService.excluirConta(senha);
      logout();
      navigate('/login');
    } catch (requestError) {
      setErroExclusao(getApiError(requestError));
    } finally {
      setExcluindo(false);
    }
  };

  const fechar = () => {
    if (excluindo) return;
    setExcluirAberto(false);
    setSenha('');
    setErroExclusao('');
  };

  return (
    <article className="panel panel--padded settings-card">
      <div className="section-heading">
        <div>
          <h2><ShieldAlert size={18} /> Privacidade e dados</h2>
          <p>Seus direitos sobre os dados da conta</p>
        </div>
      </div>

      {erro && <Feedback type="error">{erro}</Feedback>}

      <div className="entity-form">
        <p className="confirm-copy">
          Baixe uma cópia dos dados que guardamos sobre você: conta, aceites dos termos, escritórios
          e atividade. Dados de clientes e processos pertencem ao escritório.
        </p>
        <div className="form-actions">
          <button className="button button--secondary" type="button" onClick={() => void baixar()} disabled={baixando}>
            <Download size={16} /> {baixando ? 'Preparando...' : 'Baixar meus dados'}
          </button>
        </div>

        <p className="confirm-copy">
          Ao excluir a conta, seu nome, e-mail e senha são removidos e o acesso é encerrado. O histórico
          do escritório é preservado sem identificar você. Veja a{' '}
          <Link to="/privacidade" target="_blank">Política de Privacidade</Link>.
        </p>
        <div className="form-actions">
          <button className="button button--danger" type="button" onClick={() => setExcluirAberto(true)}>
            <Trash2 size={16} /> Excluir minha conta
          </button>
        </div>
      </div>

      <Modal
        open={excluirAberto}
        title="Excluir minha conta"
        description="Esta ação não pode ser desfeita."
        onClose={fechar}
      >
        <form onSubmit={excluir}>
          {erroExclusao && <Feedback type="error">{erroExclusao}</Feedback>}
          <p className="confirm-copy">
            Se você é o único proprietário de um escritório com outras pessoas, transfira a propriedade
            antes. Confirme com a sua senha para continuar.
          </p>
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
            <button className="button button--secondary" type="button" onClick={fechar} disabled={excluindo}>
              Cancelar
            </button>
            <button className="button button--danger" type="submit" disabled={excluindo}>
              {excluindo ? 'Excluindo...' : 'Excluir definitivamente'}
            </button>
          </div>
        </form>
      </Modal>
    </article>
  );
};

export default PrivacidadePanel;
