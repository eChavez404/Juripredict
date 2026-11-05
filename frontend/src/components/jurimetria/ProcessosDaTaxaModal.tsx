import { useEffect, useState } from 'react';
import { getApiError } from '../../services/api';
import { jurimetriaService, type FiltrosJurimetria } from '../../services/juripredict';
import type { JurimetriaProcessos } from '../../types';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';

type ProcessosDaTaxaModalProps = {
  /** Recorte aberto; `null` mantém o modal fechado. */
  recorte: { titulo: string; filtros: FiltrosJurimetria } | null;
  onClose: () => void;
};

const ROTULOS_RESULTADO: Record<string, string> = {
  FAVORAVEL: 'Favorável',
  ACORDO: 'Acordo',
  DESFAVORAVEL: 'Desfavorável',
};

const ProcessosDaTaxaModal = ({ recorte, onClose }: ProcessosDaTaxaModalProps) => {
  const [dados, setDados] = useState<JurimetriaProcessos | null>(null);
  const [erro, setErro] = useState('');

  useEffect(() => {
    if (!recorte) return undefined;
    let ativo = true;
    setDados(null);
    setErro('');
    jurimetriaService.processos(recorte.filtros)
      .then((resposta) => { if (ativo) setDados(resposta); })
      .catch((requestError) => { if (ativo) setErro(getApiError(requestError)); });
    return () => { ativo = false; };
  }, [recorte]);

  return (
    <Modal
      open={Boolean(recorte)}
      title="Processos que sustentam o número"
      description={recorte?.titulo}
      size="large"
      onClose={onClose}
    >
      {erro && <Feedback type="error">{erro}</Feedback>}
      {!dados && !erro && <Feedback type="info">Carregando...</Feedback>}
      {dados && (
        <>
          <p className="taxa-processos__total">
            {dados.exibidos === dados.total
              ? `${dados.total} ${dados.total === 1 ? 'processo concluído' : 'processos concluídos'}`
              : `Exibindo ${dados.exibidos} de ${dados.total} processos concluídos`}
          </p>
          <div className="table-scroll">
            <table className="data-table data-table--compacta">
              <thead><tr><th>Nº CNJ</th><th>Resultado</th><th>Cliente</th><th>Vara</th><th>Distribuição</th></tr></thead>
              <tbody>
                {dados.processos.map((processo) => (
                  <tr key={processo.id}>
                    <td>{processo.numero_cnj}</td>
                    <td>{ROTULOS_RESULTADO[processo.resultado] ?? processo.resultado}</td>
                    <td>{processo.cliente_nome}</td>
                    <td>{processo.vara}</td>
                    <td>{processo.data_distribuicao ? new Date(`${processo.data_distribuicao}T12:00:00`).toLocaleDateString('pt-BR') : 'Sem data'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Modal>
  );
};

export default ProcessosDaTaxaModal;
