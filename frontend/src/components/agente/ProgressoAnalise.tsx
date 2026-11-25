import { useEffect, useState } from 'react';
import { Check, Loader2 } from 'lucide-react';

type ProgressoAnaliseProps = {
  /** Etapa informada pelo agente, ou `ligando` enquanto ele não responde. */
  etapa: string;
  /** Há base de decisões conectada: sem ela, não se diz que os dados foram consultados. */
  comBase: boolean;
};

const formatarTempo = (segundos: number) => (segundos < 60
  ? `${segundos} s`
  : `${Math.floor(segundos / 60)} min ${String(segundos % 60).padStart(2, '0')} s`);

const ProgressoAnalise = ({ etapa, comBase }: ProgressoAnaliseProps) => {
  const [segundos, setSegundos] = useState(0);

  useEffect(() => {
    const inicio = Date.now();
    const relogio = setInterval(() => setSegundos(Math.floor((Date.now() - inicio) / 1000)), 1000);
    return () => clearInterval(relogio);
  }, []);

  const etapas = [
    { chave: 'prepare_context', rotulo: 'Separando os critérios do tema' },
    {
      chave: 'retrieve_cases',
      rotulo: comBase ? 'Buscando decisões parecidas na base do TRT-16' : 'Base de decisões ainda não conectada',
    },
    {
      chave: 'analyze_case',
      rotulo: comBase ? 'Analisando o caso com o resultado da busca' : 'Analisando o caso pelos critérios do tema',
    },
    { chave: 'measure_case', rotulo: 'Calculando os índices' },
  ];
  const atual = etapas.findIndex((item) => item.chave === etapa);

  return (
    <section className="panel panel--padded agente-progresso" aria-label="Andamento da análise">
      <div className="agente-progresso__topo">
        <Loader2 className="agente-progresso__giro" size={20} aria-hidden="true" />
        <div>
          {/* Só esta linha é anunciada: o relógio em área viva falaria a cada segundo. */}
          <strong role="status">
            {etapa === 'ligando' ? 'Ligando o agente. Pode levar até dois minutos...' : `${etapas[atual]?.rotulo ?? 'Analisando'}...`}
          </strong>
          <p>Aguardando a análise há {formatarTempo(segundos)}. Costuma levar até um minuto; pode continuar nesta página.</p>
        </div>
      </div>
      <div className="agente-progresso__barra" aria-hidden="true"><span /></div>
      <ol>
        {etapas.map((item, indice) => (
          <li
            key={item.chave}
            className={indice < atual ? 'feito' : indice === atual ? 'atual' : undefined}
            aria-current={indice === atual ? 'step' : undefined}
          >
            <span aria-hidden="true">{indice < atual ? <Check size={13} /> : indice + 1}</span>
            {item.rotulo}
          </li>
        ))}
      </ol>
    </section>
  );
};

export default ProgressoAnalise;
