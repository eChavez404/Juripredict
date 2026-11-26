import { useEffect, useState } from 'react';
import { Gavel, ListChecks } from 'lucide-react';
import { getApiError } from '../../services/api';
import { jurimetriaService, type FiltrosTribunal } from '../../services/juripredict';
import type { JurimetriaTribunal as Dados, TaxaTribunal } from '../../types';
import Feedback from '../ui/Feedback';
import DecisoesTribunalModal from './DecisoesTribunalModal';

const formatarData = (iso: string | null) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('pt-BR') : '—');

const descreverTaxa = (taxa: TaxaTribunal) => (taxa.favoravel === null || !taxa.intervalo_favoravel
  ? 'Sem taxa'
  : `${taxa.favoravel}% (de ${taxa.intervalo_favoravel.min}% a ${taxa.intervalo_favoravel.max}%)`);

const JurimetriaTribunal = () => {
  const [dados, setDados] = useState<Dados | null>(null);
  const [erro, setErro] = useState('');
  const [filtros, setFiltros] = useState<FiltrosTribunal>({ tema: 'insalubridade', vara: '', ano: '' });
  const [recorte, setRecorte] = useState<{ titulo: string; filtros: FiltrosTribunal } | null>(null);

  useEffect(() => {
    let ativo = true;
    jurimetriaService.tribunal(filtros)
      .then((resposta) => { if (ativo) { setDados(resposta); setErro(''); } })
      .catch((requestError) => { if (ativo) setErro(getApiError(requestError)); });
    return () => { ativo = false; };
  }, [filtros]);

  if (erro && !dados) return <Feedback type="error">{erro}</Feedback>;
  if (!dados) return <div className="panel empty-state">Carregando as decisões do tribunal...</div>;
  if (!dados.disponivel) {
    return (
      <div className="panel empty-state">
        A base de decisões do TRT-16 ainda não foi importada neste ambiente.
      </div>
    );
  }

  const { geral, validacao, opcoes, fonte } = dados;
  // a supressão geral (rótulo ainda não conferido) não aparece; só o motivo próprio do recorte
  const motivoDoRecorte = (motivo: string | null) => (motivo && motivo !== validacao.motivo ? motivo : undefined);
  const mudar = (campos: Partial<FiltrosTribunal>) => setFiltros((atual) => ({ ...atual, ...campos }));
  const tema = opcoes.temas.find((item) => item.valor === filtros.tema)?.rotulo ?? filtros.tema;
  const tituloRecorte = [tema, filtros.vara || 'todas as varas', filtros.ano || 'todos os anos'].join(' · ');
  const abrir = (titulo: string, extra: Partial<FiltrosTribunal> = {}) => setRecorte({ titulo, filtros: { ...filtros, ...extra } });

  return (
    <div className="tribunal">
      {erro && <Feedback type="error">{erro}</Feedback>}

      <div className="panel jurimetria-filtros" role="group" aria-label="Recorte das decisões">
        <label className="form-field">
          <span>Pedido</span>
          <select value={filtros.tema} onChange={(event) => mudar({ tema: event.target.value, vara: '', ano: '' })}>
            {opcoes.temas.map((item) => <option value={item.valor} key={item.valor}>{item.rotulo}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Vara</span>
          <select value={filtros.vara} onChange={(event) => mudar({ vara: event.target.value })}>
            <option value="">Todas</option>
            {opcoes.varas.map((vara) => <option value={vara} key={vara}>{vara}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Ano da sentença</span>
          <select value={filtros.ano} onChange={(event) => mudar({ ano: event.target.value })}>
            <option value="">Todos</option>
            {opcoes.anos.map((ano) => <option value={ano} key={ano}>{ano}</option>)}
          </select>
        </label>
      </div>

      <section className="grid tribunal-resumo" aria-label="Taxa de deferimento do recorte">
        <article className="panel panel--padded tribunal-taxa">
          <span className="eyebrow">Taxa de deferimento</span>
          <strong className="tribunal-taxa__valor">{geral.favoravel === null ? '—' : `${geral.favoravel}%`}</strong>
          {geral.intervalo_favoravel && <span className="tribunal-taxa__ic">IC 95%: {geral.intervalo_favoravel.min}% a {geral.intervalo_favoravel.max}%</span>}
          <p>Baseada em <b>{geral.total}</b> {geral.total === 1 ? 'sentença de mérito' : 'sentenças de mérito'}</p>
          <p className="field-hint">
            {geral.cobertura === null ? 'Cobertura da fonte neste recorte: não medida' : `Cobertura da fonte neste recorte: ${geral.cobertura}%`}
          </p>
          {motivoDoRecorte(geral.motivo) && <p className="tribunal-motivo">{geral.motivo}</p>}
          <button className="button button--primary tribunal-taxa__ver" type="button" disabled={!geral.total} onClick={() => abrir(tituloRecorte)}>
            <ListChecks size={16} aria-hidden="true" /> Ver as {geral.total} sentenças
          </button>
        </article>

        <article className="panel panel--padded">
          <div className="section-heading"><div><h2>Fora da taxa</h2><p>Decisões do recorte que não entram na conta, com o motivo</p></div></div>
          {dados.fora_da_taxa.length ? (
            <ul className="tribunal-fora">
              {dados.fora_da_taxa.map((item) => <li key={item.motivo}><span>{item.motivo}</span><b>{item.total}</b></li>)}
            </ul>
          ) : <p className="empty-state">Nenhuma decisão ficou de fora.</p>}
        </article>
      </section>

      <p className="tribunal-populacao"><Gavel size={15} aria-hidden="true" /> {dados.populacao}</p>

      <section className="jurimetria-comparacao" aria-label="Comparar varas e anos">
        {[
          { titulo: 'Comparar varas', cabecalho: 'Vara', linhas: dados.por_vara.map((item) => ({ chave: item.vara, rotulo: item.vara, taxa: item, extra: { vara: item.vara } })) },
          { titulo: 'Comparar anos', cabecalho: 'Ano da sentença', linhas: dados.por_ano.map((item) => ({ chave: String(item.ano), rotulo: String(item.ano), taxa: item, extra: { ano: String(item.ano) } })) },
        ].map((tabela) => (
          <article className="panel panel--padded" key={tabela.titulo}>
            <div className="section-heading"><div><h2>{tabela.titulo}</h2></div></div>
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th>{tabela.cabecalho}</th><th>Sentenças (n)</th><th>Taxa e intervalo de confiança</th><th>Conferir</th></tr></thead>
                <tbody>
                  {tabela.linhas.map((linha) => (
                    <tr key={linha.chave}>
                      <td>{linha.rotulo}</td>
                      <td>{linha.taxa.total}</td>
                      <td title={motivoDoRecorte(linha.taxa.motivo)}>{descreverTaxa(linha.taxa)}</td>
                      <td>
                        <button className="button button--secondary button--small" type="button" aria-label={`Ver sentenças: ${linha.rotulo}`} onClick={() => abrir(`${tema} · ${linha.rotulo}`, linha.extra)}>
                          Ver sentenças
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        ))}
        <p className="jurimetria-comparacao__nota">Intervalos que se sobrepõem não permitem afirmar que uma vara decide diferente da outra.</p>
      </section>

      <footer className="tribunal-rodape">
        <p><b>Critério:</b> {dados.criterio}</p>
        <p>
          <b>Fonte:</b> {fonte.origem}, sentenças de {formatarData(fonte.inicio)} a {formatarData(fonte.fim)}. Pipeline {fonte.versao}.
        </p>
      </footer>

      <DecisoesTribunalModal recorte={recorte} onClose={() => setRecorte(null)} />
    </div>
  );
};

export default JurimetriaTribunal;
