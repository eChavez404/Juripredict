import { useState, type FormEvent } from 'react';
import { MessageSquarePlus } from 'lucide-react';
import Feedback from '../ui/Feedback';
import type { AgenteCasoNovo, AgenteOpcoes } from '../../types';

type NovoCasoProps = {
  opcoes: AgenteOpcoes;
  enviando: boolean;
  onCriar: (caso: AgenteCasoNovo) => void;
};

const NovoCaso = ({ opcoes, enviando, onCriar }: NovoCasoProps) => {
  const [caso, setCaso] = useState<AgenteCasoNovo>({
    tema: opcoes.temas[0]?.value ?? '', fase: opcoes.fases[0]?.value ?? '', orgao_julgador: '', provas: [], relato: '',
  });
  const mudar = (campos: Partial<AgenteCasoNovo>) => setCaso((atual) => ({ ...atual, ...campos }));
  const alternarProva = (valor: string) => mudar({
    provas: caso.provas.includes(valor) ? caso.provas.filter((item) => item !== valor) : [...caso.provas, valor],
  });
  const enviar = (event: FormEvent) => {
    event.preventDefault();
    onCriar(caso);
  };

  return (
    <form className="panel panel--padded entity-form" onSubmit={enviar} aria-label="Novo caso">
      <div className="section-heading"><div><h2>Novo caso</h2><p>Conte o caso; depois, converse com o agente para fortalecê-lo.</p></div></div>
      <Feedback type="info">
        O texto do caso é enviado a serviços de IA de terceiros. Não informe nomes das partes. CPF, CNPJ, PIS, e-mail e telefone são mascarados antes do envio.
      </Feedback>
      <div className="form-grid">
        <label className="form-field">
          <span>Tema</span>
          <select value={caso.tema} required onChange={(event) => mudar({ tema: event.target.value })}>
            {opcoes.temas.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>Fase do processo</span>
          <select value={caso.fase} required onChange={(event) => mudar({ fase: event.target.value })}>
            {opcoes.fases.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label className="form-field form-field--full">
          <span>Relato do caso</span>
          <textarea
            className="agente-relato"
            value={caso.relato}
            required
            minLength={40}
            maxLength={4000}
            placeholder="Função, período, local, agente ou risco, EPI, o que a empresa alega..."
            onChange={(event) => mudar({ relato: event.target.value })}
          />
        </label>
        <fieldset className="prazo-conferir form-field--full">
          <legend>Provas disponíveis</legend>
          <div className="agente-provas">
            {opcoes.provas.map((item) => (
              <label className="checkbox-label" key={item.value}>
                <input type="checkbox" checked={caso.provas.includes(item.value)} onChange={() => alternarProva(item.value)} />
                {item.label}
              </label>
            ))}
          </div>
        </fieldset>
        <label className="form-field form-field--full">
          <span>Órgão julgador (opcional)</span>
          <input value={caso.orgao_julgador} maxLength={200} placeholder="Ex.: Vara do Trabalho de Balsas" onChange={(event) => mudar({ orgao_julgador: event.target.value })} />
        </label>
      </div>
      <div className="form-actions">
        <button className="button button--primary" type="submit" disabled={enviando || !opcoes.ia_configurada}>
          <MessageSquarePlus size={16} aria-hidden="true" /> {enviando ? 'Enviando...' : 'Analisar caso'}
        </button>
      </div>
    </form>
  );
};

export default NovoCaso;
