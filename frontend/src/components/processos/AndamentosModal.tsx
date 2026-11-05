import { useEffect, useState } from 'react';
import { CalendarPlus, RefreshCw } from 'lucide-react';
import { getApiError } from '../../services/api';
import { processoService } from '../../services/juripredict';
import type { Andamento, AndamentosResposta, Processo } from '../../types';
import CalculadoraPrazoModal from '../agenda/CalculadoraPrazoModal';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';

type AndamentosModalProps = {
  processo: Processo | null;
  onClose: () => void;
};

const formatarData = (valor: string) => new Intl.DateTimeFormat('pt-BR', {
  dateStyle: 'short',
  timeStyle: 'short',
}).format(new Date(valor));

const diaLocal = (valor: string) => {
  const data = new Date(valor);
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, '0')}-${String(data.getDate()).padStart(2, '0')}`;
};

const AndamentosModal = ({ processo, onClose }: AndamentosModalProps) => {
  const [prazoDe, setPrazoDe] = useState<Andamento | null>(null);
  const [dados, setDados] = useState<AndamentosResposta | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [erro, setErro] = useState('');
  const [aviso, setAviso] = useState('');

  const id = processo?.id;
  useEffect(() => {
    if (id === undefined) return;
    let ativo = true;
    setDados(null);
    setErro('');
    setAviso('');
    setPrazoDe(null);
    setLoading(true);
    processoService.andamentos(id)
      .then((resposta) => { if (ativo) setDados(resposta); })
      .catch((requestError) => { if (ativo) setErro(getApiError(requestError)); })
      .finally(() => { if (ativo) setLoading(false); });
    return () => { ativo = false; };
  }, [id]);

  const sincronizar = async () => {
    if (id === undefined) return;
    setBusy(true);
    setErro('');
    setAviso('');
    try {
      const { novos, ...resposta } = await processoService.sincronizarAndamentos(id);
      setDados(resposta);
      setAviso(novos === 0
        ? 'Nenhum andamento novo.'
        : `${novos} ${novos === 1 ? 'andamento novo' : 'andamentos novos'}.`);
    } catch (requestError) {
      setErro(getApiError(requestError));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
    <Modal
      open={Boolean(processo) && !prazoDe}
      title="Andamentos"
      description={processo ? `Processo ${processo.numero_cnj}, lido do DataJud (CNJ).` : undefined}
      size="large"
      onClose={onClose}
    >
      <div className="andamentos">
        <div className="andamentos__topo">
          <small>
            {dados?.sincronizado_em
              ? `Última leitura em ${formatarData(dados.sincronizado_em)}`
              : 'Ainda não consultado.'}
          </small>
          <button className="button button--secondary button--small" type="button" onClick={sincronizar} disabled={busy}>
            <RefreshCw size={14} /> {busy ? 'Consultando...' : 'Atualizar agora'}
          </button>
        </div>

        {erro && <Feedback type="error">{erro}</Feedback>}
        {aviso && <Feedback type="success">{aviso}</Feedback>}
        {loading && <Feedback type="info">Carregando...</Feedback>}

        {dados && dados.andamentos.length === 0 && !loading && (
          <p className="andamentos__vazio">
            Nenhum andamento registrado. Processos em segredo de justiça ou ainda não
            publicados no DataJud não aparecem.
          </p>
        )}

        {dados && dados.andamentos.length > 0 && (
          <ol className="andamentos__lista">
            {dados.andamentos.map((item) => (
              <li key={item.id}>
                <time dateTime={item.data_hora}>{formatarData(item.data_hora)}</time>
                <strong>{item.nome}</strong>
                {item.complemento && <span>{item.complemento}</span>}
                <button className="button button--secondary button--small andamentos__prazo" type="button" onClick={() => setPrazoDe(item)}>
                  <CalendarPlus size={14} /> Criar prazo
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Modal>
    <CalculadoraPrazoModal
      open={Boolean(prazoDe)}
      processo={processo}
      dataBase={prazoDe ? diaLocal(prazoDe.data_hora) : ''}
      titulo={prazoDe ? `Prazo: ${prazoDe.nome}` : ''}
      onClose={() => setPrazoDe(null)}
      onCriado={() => setAviso('Prazo adicionado à agenda. O lembrete sai por e-mail 24 horas antes.')}
    />
    </>
  );
};

export default AndamentosModal;
