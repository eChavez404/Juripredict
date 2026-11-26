import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Send, Trash2 } from 'lucide-react';
import ConfirmDialog from '../ui/ConfirmDialog';
import Feedback from '../ui/Feedback';
import AnaliseCompleta from './AnaliseCompleta';
import { SeletorProcesso } from './NovoCaso';
import ProgressoAnalise from './ProgressoAnalise';
import type { AgenteOpcoes, CasoEstudo, DadosDoCaso, Processo } from '../../types';

type ConversaProps = {
  caso: CasoEstudo;
  opcoes: AgenteOpcoes;
  enviando: boolean;
  onEnviar: (texto: string) => Promise<boolean>;
  processos: Processo[];
  onAtualizar: (dados: DadosDoCaso) => void;
  onExcluir: () => void;
};

const rotulo = (lista: AgenteOpcoes['temas'], valor: string) => lista.find((item) => item.value === valor)?.label ?? valor;

const variacao = (atual: number, anterior?: number | null) => {
  if (anterior == null) return '';
  const diferenca = atual - anterior;
  return diferenca === 0 ? ' (sem mudança)' : ` (${diferenca > 0 ? '+' : ''}${diferenca} desde a análise anterior)`;
};

const Conversa = ({ caso, opcoes, processos, enviando, onEnviar, onAtualizar, onExcluir }: ConversaProps) => {
  const [texto, setTexto] = useState('');
  const [dados, setDados] = useState<DadosDoCaso>({
    fase: caso.fase, orgao_julgador: caso.orgao_julgador, provas: caso.provas, processo: caso.processo,
  });
  const [excluindo, setExcluindo] = useState(false);
  const fim = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLTextAreaElement>(null);

  const pendente = caso.mensagens.some((mensagem) => mensagem.status === 'pendente');
  const analises = caso.mensagens.filter((mensagem) => mensagem.indice_atual !== null);
  const ultima = analises.at(-1);

  useEffect(() => { fim.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }); }, [caso.mensagens.length, pendente]);

  const enviar = async (event: FormEvent) => {
    event.preventDefault();
    if (await onEnviar(texto.trim())) setTexto('');
  };

  const responder = (pergunta: string) => {
    setTexto(`${pergunta}\nResposta: `);
    campo.current?.focus();
  };

  const alternarProva = (valor: string) => setDados((atual) => ({
    ...atual,
    provas: atual.provas.includes(valor) ? atual.provas.filter((item) => item !== valor) : [...atual.provas, valor],
  }));

  return (
    <section className="agente-conversa" aria-label="Conversa sobre o caso">
      <header className="panel panel--padded agente-cabecalho">
        <div>
          <span className="eyebrow">{rotulo(opcoes.temas, caso.tema)} · {rotulo(opcoes.fases, caso.fase)}</span>
          <h2>{caso.titulo || 'Caso em análise'}</h2>
        </div>
        <button className="button button--secondary button--small" type="button" onClick={() => setExcluindo(true)}>
          <Trash2 size={15} aria-hidden="true" /> Excluir caso
        </button>
      </header>

      {analises.length > 0 && (
        <div className="panel panel--padded agente-evolucao" aria-label="Evolução do caso">
          <div>
            <span className="eyebrow">Como o caso evoluiu</span>
            <ol>
              {analises.map((mensagem, indice) => (
                <li key={mensagem.id}>
                  <small>Análise {indice + 1}</small>
                  <strong>{mensagem.indice_atual}</strong>
                </li>
              ))}
            </ol>
          </div>
          {ultima && (
            <p>
              Índice atual <b>{ultima.indice_atual}</b> de 100{variacao(ultima.indice_atual ?? 0, analises.at(-2)?.indice_atual)}.
              Com as melhorias propostas, pode chegar a <b>{ultima.indice_potencial}</b>. Mede quanto do que o tema exige está demonstrado; não é probabilidade de êxito.
            </p>
          )}
        </div>
      )}

      <details className="panel panel--padded agente-dados">
        <summary>Dados do caso (valem para a próxima mensagem)</summary>
        <div className="form-grid">
          <label className="form-field">
            <span>Fase do processo</span>
            <select value={dados.fase} onChange={(event) => setDados({ ...dados, fase: event.target.value })}>
              {opcoes.fases.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label className="form-field">
            <span>Órgão julgador</span>
            <input value={dados.orgao_julgador} maxLength={200} onChange={(event) => setDados({ ...dados, orgao_julgador: event.target.value })} />
          </label>
          <fieldset className="prazo-conferir form-field--full">
            <legend>Provas disponíveis</legend>
            <div className="agente-provas">
              {opcoes.provas.map((item) => (
                <label className="checkbox-label" key={item.value}>
                  <input type="checkbox" checked={dados.provas.includes(item.value)} onChange={() => alternarProva(item.value)} />
                  {item.label}
                </label>
              ))}
            </div>
          </fieldset>
          <SeletorProcesso processos={processos} valor={dados.processo} onMudar={(processo) => setDados({ ...dados, processo })} />
        </div>
        <div className="form-actions">
          <button className="button button--secondary button--small" type="button" onClick={() => onAtualizar(dados)}>Salvar dados do caso</button>
        </div>
      </details>

      <ol className="agente-mensagens">
        {caso.mensagens.map((mensagem) => {
          if (mensagem.autor === 'advogado') {
            return (
              <li key={mensagem.id} className="agente-bolha agente-bolha--advogado">
                <p>{mensagem.texto}</p>
                {mensagem.documentos_lidos.length > 0 && (
                  <small>Do processo: {mensagem.documentos_lidos.map((doc) => `${doc.nome} (${doc.situacao})`).join(', ')}</small>
                )}
              </li>
            );
          }
          if (mensagem.status === 'pendente') {
            return <li key={mensagem.id}><ProgressoAnalise etapa={caso.etapa ?? 'prepare_context'} comBase={opcoes.base_configurada} /></li>;
          }
          if (mensagem.status === 'erro') {
            return <li key={mensagem.id}><Feedback type="error">{mensagem.erro || 'Não foi possível analisar o caso.'}</Feedback></li>;
          }
          const anterior = analises[analises.indexOf(mensagem) - 1];
          return (
            <li key={mensagem.id} className="agente-bolha agente-bolha--agente">
              <span className="eyebrow">Agente JuriPredict</span>
              <p>{mensagem.texto}</p>
              {mensagem.resultado?.aviso && <Feedback type="info">{mensagem.resultado.aviso}</Feedback>}
              {mensagem.indice_atual !== null && (
                <small>Índice {mensagem.indice_atual}{variacao(mensagem.indice_atual, anterior?.indice_atual)} · potencial {mensagem.indice_potencial}</small>
              )}
              {(mensagem.resultado?.analise.perguntas ?? []).length > 0 && (
                <div className="agente-perguntas">
                  <span>O que ainda falta saber:</span>
                  {mensagem.resultado?.analise.perguntas.map((pergunta) => (
                    <button key={pergunta} type="button" className="button button--secondary button--small" onClick={() => responder(pergunta)} disabled={pendente}>
                      {pergunta}
                    </button>
                  ))}
                </div>
              )}
              {mensagem.resultado && (
                <details className="agente-completa">
                  <summary>Ver análise completa</summary>
                  <AnaliseCompleta resultado={mensagem.resultado} />
                </details>
              )}
            </li>
          );
        })}
      </ol>
      <div ref={fim} />

      <form className="panel panel--padded agente-composer" onSubmit={(event) => void enviar(event)}>
        <label className="form-field">
          <span>Acrescente um fato, uma prova ou uma resposta</span>
          <textarea
            ref={campo}
            value={texto}
            minLength={2}
            maxLength={4000}
            required
            placeholder="Ex.: o perito constatou contato com agentes biológicos; a empresa não juntou fichas de EPI."
            onChange={(event) => setTexto(event.target.value)}
          />
        </label>
        <div className="form-actions">
          <small className="field-hint">{texto.length} de 4000 caracteres</small>
          <button className="button button--primary" type="submit" disabled={pendente || enviando || !texto.trim()}>
            <Send size={16} aria-hidden="true" /> {pendente ? 'Aguardando a análise...' : 'Enviar'}
          </button>
        </div>
      </form>

      <ConfirmDialog
        open={excluindo}
        title="Excluir caso"
        message="A conversa e as análises deste caso serão apagadas. Isso não pode ser desfeito."
        onCancel={() => setExcluindo(false)}
        onConfirm={() => { setExcluindo(false); onExcluir(); }}
      />
    </section>
  );
};

export default Conversa;
