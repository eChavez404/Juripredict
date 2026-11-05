import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { useAuth } from '../../contexts/auth';
import { pendenciaService } from '../../services/juripredict';
import type { EventoAgenda, Pendencias } from '../../types';

const diaLocal = (valor: string) => {
  const data = new Date(valor);
  const mes = String(data.getMonth() + 1).padStart(2, '0');
  const dia = String(data.getDate()).padStart(2, '0');
  return `${data.getFullYear()}-${mes}-${dia}`;
};

const formatarQuando = (valor: string) => new Date(valor).toLocaleString('pt-BR', {
  day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
});
const formatarDia = (valor: string) => new Date(valor).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });

const CentralPendencias = () => {
  const { activeEscritorio } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [dados, setDados] = useState<Pendencias | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [aberto, setAberto] = useState(false);
  const raiz = useRef<HTMLDivElement>(null);
  const escritorioId = activeEscritorio?.id;

  const carregar = useCallback(() => {
    if (!escritorioId) return;
    pendenciaService.get()
      .then((resposta) => { setDados(resposta); setFalhou(false); })
      // não bloqueia o app: o sino só deixa de mostrar o número
      .catch(() => { setDados(null); setFalhou(true); });
  }, [escritorioId]);

  // A cada navegação: concluir um prazo na agenda precisa baixar o número do sino.
  useEffect(() => { carregar(); }, [carregar, location.pathname]);

  useEffect(() => {
    if (!aberto) return undefined;
    const fecharAoClicarFora = (event: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(event.target as Node)) setAberto(false);
    };
    const fecharComEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setAberto(false);
    };
    document.addEventListener('mousedown', fecharAoClicarFora);
    document.addEventListener('keydown', fecharComEsc);
    return () => {
      document.removeEventListener('mousedown', fecharAoClicarFora);
      document.removeEventListener('keydown', fecharComEsc);
    };
  }, [aberto]);

  const ir = (caminho: string) => {
    setAberto(false);
    navigate(caminho);
  };

  const urgentes = dados?.urgentes ?? 0;
  const rotulo = urgentes
    ? `Pendências: ${urgentes} ${urgentes === 1 ? 'urgente' : 'urgentes'}`
    : 'Pendências';

  const itemDeEvento = (evento: EventoAgenda, quando: string) => (
    <li key={evento.id}>
      <button type="button" onClick={() => ir(`/agenda?data=${diaLocal(evento.inicio)}`)}>
        <strong>{evento.titulo}</strong>
        <small>{quando}{evento.processo_numero ? ` · ${evento.processo_numero}` : ''}</small>
      </button>
    </li>
  );

  const semPendencias = dados && !dados.vencidos.length && !dados.proximos.length && !dados.andamentos_recentes.length;

  return (
    <div className="pendencias" ref={raiz}>
      <button
        className="icon-button"
        type="button"
        aria-label={rotulo}
        aria-expanded={aberto}
        onClick={() => { if (!aberto) carregar(); setAberto(!aberto); }}
      >
        <Bell size={18} />
        {urgentes > 0 && <span className="pendencias__contador" aria-hidden="true">{urgentes > 99 ? '99+' : urgentes}</span>}
      </button>

      {aberto && (
        <section className="pendencias__painel" aria-label="Pendências do escritório">
          <h2>Pendências</h2>
          {falhou && <p className="pendencias__vazio">Não foi possível carregar agora.</p>}
          {!falhou && !dados && <p className="pendencias__vazio">{escritorioId ? 'Carregando...' : 'Selecione um escritório.'}</p>}
          {semPendencias && <p className="pendencias__vazio">Nada pendente nos próximos 7 dias.</p>}

          {dados && dados.vencidos.length > 0 && (
            <div className="pendencias__grupo pendencias__grupo--vencidos">
              <h3>Prazos vencidos ({dados.total_vencidos})</h3>
              <ul>{dados.vencidos.map((evento) => itemDeEvento(evento, `Venceu em ${formatarDia(evento.inicio)}`))}</ul>
            </div>
          )}
          {dados && dados.proximos.length > 0 && (
            <div className="pendencias__grupo">
              <h3>Próximos 7 dias ({dados.total_proximos})</h3>
              <ul>{dados.proximos.map((evento) => itemDeEvento(evento, formatarQuando(evento.inicio)))}</ul>
            </div>
          )}
          {dados && dados.andamentos_recentes.length > 0 && (
            <div className="pendencias__grupo">
              <h3>Andamentos recentes</h3>
              <ul>
                {dados.andamentos_recentes.map((andamento) => (
                  <li key={andamento.id}>
                    <button type="button" onClick={() => ir('/processos')}>
                      <strong>{andamento.nome}</strong>
                      <small>{formatarDia(andamento.data_hora)} · {andamento.processo_numero}</small>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <button className="button button--secondary button--small pendencias__agenda" type="button" onClick={() => ir('/agenda')}>
            Abrir agenda
          </button>
        </section>
      )}
    </div>
  );
};

export default CentralPendencias;
