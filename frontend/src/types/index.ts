export type Usuario = {
  id: number;
  username: string;
  email: string;
  nome: string;
  // ausente em sessões gravadas antes da verificação de e-mail existir
  email_verificado?: boolean;
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
  andamentos_sincronizados_em: string | null;
  arquivo_peticao_inicial_url: string | null;
  criado_em: string;
  atualizado_em: string;
};

export type Andamento = {
  id: number;
  data_hora: string;
  codigo: number | null;
  nome: string;
  complemento: string;
};

export type DocumentoProcesso = {
  id: number;
  nome: string;
  tamanho: number;
  url: string;
  enviado_por_nome: string | null;
  criado_em: string;
};

export type AndamentosResposta = {
  sincronizado_em: string | null;
  andamentos: Andamento[];
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

export type IntervaloPercentual = { min: number; max: number };

// Uma taxa só existe com o contexto que a sustenta: quantos casos e qual a
// incerteza. Abaixo do piso de amostra ela vem nula, com o motivo.
export type TaxaVara = {
  vara: string;
  total: number;
  suficiente: boolean;
  favoravel: number | null;
  desfavoravel: number | null;
  intervalo_favoravel: IntervaloPercentual | null;
  motivo: string | null;
};

export type TaxaAno = Omit<TaxaVara, 'vara'> & { ano: number | null };

export type JurimetriaData = {
  total_analisados: number;
  taxa_favoravel: number | null;
  intervalo_favoravel: IntervaloPercentual | null;
  amostra_suficiente: boolean;
  piso_amostra: number;
  processos_ativos: number;
  por_vara: TaxaVara[];
  por_ano: TaxaAno[];
  resultados: Array<{ name: string; value: number }>;
  filtros: { area: string | null; ano: string | null };
  opcoes: { areas: Array<{ valor: string; rotulo: string }>; anos: number[] };
  insight: string;
};

export type ProcessoResumo = Pick<
  Processo,
  'id' | 'numero_cnj' | 'titulo' | 'vara' | 'comarca' | 'area' | 'resultado' | 'status' | 'data_distribuicao' | 'cliente_nome'
>;

export type JurimetriaProcessos = { total: number; exibidos: number; processos: ProcessoResumo[] };

export type PrazoTipo = 'INTIMACAO' | 'PUBLICACAO_DIARIO';
export type DiaDaMemoria = { data: string; motivo: string };

export type PrazoCalculado = {
  data_base: string;
  dias: number;
  tipo: PrazoTipo;
  area: string;
  fundamento: string;
  marco_inicial: string;
  primeiro_dia_contado: string;
  vencimento: string;
  fins_de_semana_nao_contados: number;
  dias_nao_contados: DiaDaMemoria[];
  dias_a_conferir: DiaDaMemoria[];
  ressalvas: string[];
};

export type Pendencias = {
  urgentes: number;
  total_vencidos: number;
  total_proximos: number;
  vencidos: EventoAgenda[];
  proximos: EventoAgenda[];
  andamentos_recentes: Array<{ id: number; processo: number; processo_numero: string; data_hora: string; nome: string }>;
};
