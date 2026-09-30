export type Usuario = {
  id: number;
  username: string;
  email: string;
  nome: string;
};

export type Cliente = {
  id: number;
  nome: string;
  cpf_cnpj: string;
  email: string | null;
  telefone: string | null;
  tipo: 'PF' | 'PJ';
  processos_count: number;
  criado_em: string;
  atualizado_em: string;
};

export type ClientePayload = Pick<Cliente, 'nome' | 'cpf_cnpj' | 'email' | 'telefone' | 'tipo'>;

export type ProcessoStatus = 'ATIVO' | 'SUSPENSO' | 'ARQUIVADO';
export type ProcessoResultado = 'PENDENTE' | 'FAVORAVEL' | 'DESFAVORAVEL' | 'ACORDO';
export type ProcessoArea = 'TRABALHISTA' | 'CIVEL' | 'PREVIDENCIARIO' | 'TRIBUTARIO' | 'CRIMINAL' | 'OUTRO';

export type Processo = {
  id: number;
  numero_cnj: string;
  titulo: string;
  area: ProcessoArea;
  vara: string;
  comarca: string;
  cliente: number;
  cliente_nome: string;
  parte_contraria: string;
  status: ProcessoStatus;
  resultado: ProcessoResultado;
  valor_causa: string | null;
  data_distribuicao: string | null;
  observacoes: string;
  arquivo_peticao_inicial_url: string | null;
  criado_em: string;
  atualizado_em: string;
};

export type EventoTipo = 'AUDIENCIA' | 'PRAZO' | 'REUNIAO' | 'OUTRO';

export type EventoAgenda = {
  id: number;
  titulo: string;
  tipo: EventoTipo;
  inicio: string;
  fim: string | null;
  processo: number | null;
  processo_numero: string | null;
  cliente_nome: string | null;
  local: string;
  descricao: string;
  concluido: boolean;
  criado_em: string;
  atualizado_em: string;
};

export type DashboardData = {
  metricas: {
    processos_ativos: number;
    novos_clientes_mes: number;
    prazos_semana: number;
    audiencias_proximas: number;
  };
  evolucao_processos: Array<{ mes: string; ativos: number; novos: number }>;
  status_processos: Array<{ name: string; value: number }>;
  prazos_semana: Array<{ dia: string; qtd: number }>;
  processos_recentes: Processo[];
  proximos_eventos: EventoAgenda[];
};

export type JurimetriaData = {
  total_analisados: number;
  taxa_favoravel: number;
  processos_ativos: number;
  por_vara: Array<{ vara: string; favoravel: number; desfavoravel: number; total: number }>;
  resultados: Array<{ name: string; value: number }>;
  insight: string;
};
