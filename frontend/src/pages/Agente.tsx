import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Plus } from 'lucide-react';
import Conversa from '../components/agente/Conversa';
import NovoCaso from '../components/agente/NovoCaso';
import ProtectedContent from '../components/auth/ProtectedContent';
import Feedback from '../components/ui/Feedback';
import PageHeader from '../components/ui/PageHeader';
import { useAuth } from '../contexts/auth';
import { CAPABILITIES } from '../features/escritorios/types';
import { getApiError } from '../services/api';
import { agenteService, processoService } from '../services/juripredict';
import type { AgenteCasoNovo, AgenteOpcoes, CasoEstudo, CasoEstudoResumo, DadosDoCaso, Processo } from '../types';

const INTERVALO_MS = 2000;
// O agente liga depois do site: ao acordar da hibernação do plano gratuito, demora um pouco mais.
const ESPERA_AGENTE_MS = 2 * 60 * 1000;
const NOVA_TENTATIVA_MS = 5000;
const LIGANDO = 'Ligando o agente. Pode levar até dois minutos...';

const esperar = (ms: number) => new Promise((resolve) => { setTimeout(resolve, ms); });

// Insiste enquanto o backend responde 502 (agente sem resposta). Só para leituras: repetir o
// envio do caso poderia pagar duas análises.
const insistir = async <T,>(leitura: () => Promise<T>, continuar: () => boolean, aoEsperar?: () => void): Promise<T> => {
  const limite = Date.now() + ESPERA_AGENTE_MS;
  for (;;) {
    try {
      return await leitura();
    } catch (requestError) {
      const semResposta = axios.isAxiosError(requestError) && requestError.response?.status === 502;
      if (!semResposta || Date.now() > limite || !continuar()) throw requestError;
      aoEsperar?.();
      await esperar(NOVA_TENTATIVA_MS);
    }
  }
};

const formatarData = (iso: string) => new Date(iso).toLocaleDateString('pt-BR');

const AgenteConteudo = () => {
  const [opcoes, setOpcoes] = useState<AgenteOpcoes | null>(null);
  const [casos, setCasos] = useState<CasoEstudoResumo[]>([]);
  const [processos, setProcessos] = useState<Processo[]>([]);
  const [selecionado, setSelecionado] = useState<number | 'novo'>('novo');
  const [caso, setCaso] = useState<CasoEstudo | null>(null);
  const [erro, setErro] = useState('');
  const [ligando, setLigando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const ativo = useRef(true);
  const continuar = useCallback(() => ativo.current, []);

  const recarregarLista = useCallback(() => agenteService.casos()
    .then((lista) => { if (ativo.current) setCasos(lista); })
    .catch((requestError) => { if (ativo.current) setErro(getApiError(requestError)); }), []);

  useEffect(() => {
    // Próprio deste efeito: o ref volta a valer na remontagem e duas esperas correriam juntas.
    let montado = true;
    ativo.current = true;
    insistir(agenteService.opcoes, () => montado, () => { if (montado) setLigando(true); })
      .then((resposta) => { if (montado) setOpcoes(resposta); })
      .catch((requestError) => { if (montado) setErro(getApiError(requestError)); })
      .finally(() => { if (montado) setLigando(false); });
    void recarregarLista();
    // opcional: sem a lista, o caso só não pode ser vinculado a um processo
    processoService.list().then((lista) => { if (montado) setProcessos(lista); }).catch(() => undefined);
    return () => { montado = false; ativo.current = false; };
  }, [recarregarLista]);

  const abrir = (id: number | 'novo') => {
    setSelecionado(id);
    setCaso(null);
    setErro('');
    if (id === 'novo') return;
    agenteService.caso(id)
      .then((resposta) => { if (ativo.current) setCaso(resposta); })
      .catch((requestError) => { if (ativo.current) setErro(getApiError(requestError)); });
  };

  // Enquanto o agente analisa, pergunta ao servidor; ao terminar, a lista ganha título e índice.
  const pendente = caso?.mensagens.some((mensagem) => mensagem.status === 'pendente') ?? false;
  useEffect(() => {
    if (!caso || !pendente) return undefined;
    const relogio = setTimeout(() => {
      agenteService.caso(caso.id)
        .then((resposta) => {
          if (!ativo.current) return;
          setCaso(resposta);
          if (!resposta.mensagens.some((mensagem) => mensagem.status === 'pendente')) void recarregarLista();
        })
        .catch(() => { /* passageiro: a próxima volta tenta de novo */ setCaso((atual) => (atual ? { ...atual } : atual)); });
    }, INTERVALO_MS);
    return () => clearTimeout(relogio);
  }, [caso, pendente, recarregarLista]);

  const acordarAgente = () => insistir(agenteService.opcoes, continuar, () => { if (ativo.current) setLigando(true); })
    .finally(() => { if (ativo.current) setLigando(false); });

  const criar = async (dados: AgenteCasoNovo) => {
    setErro('');
    setEnviando(true);
    try {
      // Escrever o relato pode levar mais que os 15 minutos até a hibernação: confere antes de enviar.
      await acordarAgente();
      const novo = await agenteService.criar(dados);
      if (!ativo.current) return;
      setCaso(novo);
      setSelecionado(novo.id);
      void recarregarLista();
    } catch (requestError) {
      if (ativo.current) setErro(getApiError(requestError));
    } finally {
      if (ativo.current) setEnviando(false);
    }
  };

  const enviar = async (texto: string) => {
    if (!caso) return false;
    setErro('');
    setEnviando(true);
    try {
      await acordarAgente();
      const atualizado = await agenteService.enviar(caso.id, texto);
      if (ativo.current) setCaso(atualizado);
      return true;
    } catch (requestError) {
      if (ativo.current) setErro(getApiError(requestError));
      return false;
    } finally {
      if (ativo.current) setEnviando(false);
    }
  };

  const atualizar = async (dados: DadosDoCaso) => {
    if (!caso) return;
    try {
      setCaso(await agenteService.atualizar(caso.id, dados));
      void recarregarLista();
    } catch (requestError) {
      setErro(getApiError(requestError));
    }
  };

  const excluir = async () => {
    if (!caso) return;
    try {
      await agenteService.excluir(caso.id);
      abrir('novo');
      void recarregarLista();
    } catch (requestError) {
      setErro(getApiError(requestError));
    }
  };

  return (
    <div className="page">
      <PageHeader
        eyebrow="Inteligência jurídica"
        title="Agente de IA"
        description="Estruture o caso conversando com o agente: cada informação nova é analisada contra os critérios do tema e contra decisões do TRT-16 que deram certo e que não deram."
        backTo="/"
      />

      {erro && <Feedback type="error">{erro}</Feedback>}
      {ligando && <Feedback type="info">{LIGANDO}</Feedback>}
      {opcoes && !opcoes.ia_configurada && (
        <Feedback type="error">A chave da IA (GOOGLE_API_KEY) não chegou ao agente. Confira o ambiente do servidor.</Feedback>
      )}

      {opcoes && (
        <div className="agente-layout">
          <nav className="panel agente-casos" aria-label="Seus casos">
            <button className="button button--primary agente-casos__novo" type="button" onClick={() => abrir('novo')}>
              <Plus size={16} aria-hidden="true" /> Novo caso
            </button>
            {casos.length === 0 && <p className="field-hint">Os casos analisados ficam aqui, para continuar depois.</p>}
            <ul>
              {casos.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={selecionado === item.id ? 'agente-casos__item agente-casos__item--ativo' : 'agente-casos__item'}
                    aria-current={selecionado === item.id ? 'true' : undefined}
                    onClick={() => abrir(item.id)}
                  >
                    <strong>{item.titulo || 'Caso em análise'}</strong>
                    <small>
                      {formatarData(item.atualizado_em)}
                      {item.indice_atual !== null && ` · índice ${item.indice_atual}`}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          {selecionado === 'novo' && <NovoCaso opcoes={opcoes} processos={processos} enviando={enviando} onCriar={(dados) => void criar(dados)} />}
          {selecionado !== 'novo' && caso && (
            <Conversa
              key={caso.id}
              caso={caso}
              opcoes={opcoes}
              processos={processos}
              enviando={enviando}
              onEnviar={enviar}
              onAtualizar={(dados) => void atualizar(dados)}
              onExcluir={() => void excluir()}
            />
          )}
        </div>
      )}
    </div>
  );
};

const Agente = () => {
  const { activeEscritorio } = useAuth();
  return (
    <ProtectedContent capability={CAPABILITIES.agenteUsar}>
      {/* A chave recomeça a tela ao trocar de escritório: o caso de um não fica à vista no outro. */}
      <AgenteConteudo key={activeEscritorio?.id} />
    </ProtectedContent>
  );
};

export default Agente;
