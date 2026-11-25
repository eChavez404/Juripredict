import { Fragment, useEffect, useState } from 'react';
import { getApiError } from '../../services/api';
import { jurimetriaService, type FiltrosTribunal } from '../../services/juripredict';
import type { DecisoesTribunal, ResultadoTribunal } from '../../types';
import Feedback from '../ui/Feedback';
import Modal from '../ui/Modal';

type DecisoesTribunalModalProps = {
  /** Recorte aberto; `null` mantém o modal fechado. */
  recorte: { titulo: string; filtros: FiltrosTribunal } | null;
  onClose: () => void;
};

const RESULTADOS: Record<ResultadoTribunal, string> = { deferido: 'Deferido', indeferido: 'Indeferido' };
const COMO_FOI_LIDO: Record<string, string> = {
  regra_direta: 'Lido no dispositivo',
  regra_inferida_global: 'Inferido do resultado geral',
  regra_inferida_fundamentacao: 'Inferido da fundamentação',
  regra_so_reflexo: 'Lido no dispositivo',
};
const GRAUS: Record<number, string> = { 10: 'Mínimo (10%)', 20: 'Médio (20%)', 40: 'Máximo (40%)', 30: '30%' };

const formatarData = (iso: string | null) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR') : 'Sem data');

const DecisoesTribunalModal = ({ recorte, onClose }: DecisoesTribunalModalProps) => {
  const [resultado, setResultado] = useState<ResultadoTribunal | ''>('');
  const [dados, setDados] = useState<DecisoesTribunal | null>(null);
  const [aberta, setAberta] = useState<string | null>(null);
  const [erro, setErro] = useState('');

  useEffect(() => { setResultado(''); }, [recorte]);

  useEffect(() => {
    if (!recorte) return undefined;
    let ativo = true;
    setDados(null);
    setErro('');
    setAberta(null);
    jurimetriaService.decisoesTribunal({ ...recorte.filtros, resultado })
      .then((resposta) => { if (ativo) setDados(resposta); })
      .catch((requestError) => { if (ativo) setErro(getApiError(requestError)); });
    return () => { ativo = false; };
  }, [recorte, resultado]);

  const opcoes: Array<[ResultadoTribunal | '', string]> = [
    ['', `Todas (${(dados?.contagem.deferido ?? 0) + (dados?.contagem.indeferido ?? 0)})`],
    ['deferido', `Deferidas (${dados?.contagem.deferido ?? 0})`],
    ['indeferido', `Indeferidas (${dados?.contagem.indeferido ?? 0})`],
  ];

  return (
    <Modal open={Boolean(recorte)} title="Sentenças que sustentam o número" description={recorte?.titulo} size="large" onClose={onClose}>
      {erro && <Feedback type="error">{erro}</Feedback>}
      <div className="view-toggle tribunal-resultados" role="group" aria-label="Filtrar por resultado">
        {opcoes.map(([valor, rotulo]) => (
          <button
            key={valor || 'todas'}
            type="button"
            className={resultado === valor ? 'view-toggle__button view-toggle__button--active' : 'view-toggle__button'}
            aria-pressed={resultado === valor}
            onClick={() => setResultado(valor)}
          >
            {rotulo}
          </button>
        ))}
      </div>
      {!dados && !erro && <Feedback type="info">Carregando...</Feedback>}
      {dados && (
        <>
          <p className="taxa-processos__total">
            {dados.exibidos === dados.total
              ? `${dados.total} ${dados.total === 1 ? 'sentença' : 'sentenças'}`
              : `Exibindo as ${dados.exibidos} mais recentes de ${dados.total} sentenças`}
          </p>
          <div className="table-scroll">
            <table className="data-table data-table--compacta">
              <thead><tr><th>Processo</th><th>Data</th><th>Vara</th><th>Resultado</th><th>Grau</th><th>Como foi lido</th><th>Trecho</th></tr></thead>
              <tbody>
                {dados.decisoes.map((decisao) => {
                  const chave = decisao.numero_cnj;
                  return (
                    <Fragment key={chave}>
                    <tr>
                      <td>{decisao.numero_cnj}</td>
                      <td>{formatarData(decisao.data_sentenca)}</td>
                      <td>{decisao.vara}</td>
                      <td>{RESULTADOS[decisao.resultado] ?? decisao.resultado}</td>
                      <td>{decisao.grau ? GRAUS[decisao.grau] ?? `${decisao.grau}%` : '—'}</td>
                      <td>{COMO_FOI_LIDO[decisao.mecanismo] ?? decisao.mecanismo}</td>
                      <td>
                        {decisao.trecho ? (
                          <button className="button button--secondary button--small" type="button" aria-expanded={aberta === chave} onClick={() => setAberta(aberta === chave ? null : chave)}>
                            {aberta === chave ? 'Ocultar' : 'Ver trecho'}
                          </button>
                        ) : '—'}
                      </td>
                    </tr>
                    {aberta === chave && (
                      <tr>
                        <td colSpan={7}>
                          <blockquote className="tribunal-trecho">
                            <small>Trecho do dispositivo · {decisao.numero_cnj}</small>
                            <p>{decisao.trecho}</p>
                          </blockquote>
                        </td>
                      </tr>
                    )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="field-hint">
            Resultado extraído por regra sobre o dispositivo. Nomes das partes substituídos por [parte]. Confira o inteiro teor pelo número do processo.
          </p>
        </>
      )}
    </Modal>
  );
};

export default DecisoesTribunalModal;
