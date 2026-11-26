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

// Agente de IA: espelha agente/app/agents/analista/schema.py.
export type AgenteOpcao = { value: string; label: string };
export type AgenteOpcoes = {
  ia_configurada: boolean;
  base_configurada: boolean;
  temas: AgenteOpcao[];
  fases: AgenteOpcao[];
  provas: AgenteOpcao[];
};

export type AgenteSituacao = 'atendido' | 'parcial' | 'ausente' | 'nao_aplicavel';

export type AgenteResultado = {
  analise: {
    titulo: string;
    resumo: string;
    criterios: Array<{ criterio_id: string; situacao: AgenteSituacao; evidencia: string }>;
    melhorias: Array<{ criterio_id: string; acao: string; justificativa: string; caso_ids: string[] }>;
    casos_proximos: Array<{ caso_id: string; semelhancas: string; diferencas: string }>;
    riscos: string[];
    resposta: string;
    perguntas: string[];
  };
  catalogo: { versao: string; criterios: Array<{ id: string; nome: string; fundamentos: string[] }> };
  medicao: {
    indice_atual: number;
    indice_potencial: number;
    ganho: number;
    alertas: string[];
    pontos_fortes: string[];
  };
  casos: Array<{
    id_sentenca: string;
    numero_cnj: string | null;
    tipo_documento: string | null;
    orgao_julgador: string | null;
    data_julgamento: string | null;
    resultado: string | null;
    similaridade: number;
  }>;
  suposicoes: string[];
  disclaimer: string;
};

export type AgenteCasoNovo = {
  tema: string;
  fase: string;
  orgao_julgador: string;
  provas: string[];
  processo: number | null;
  relato: string;
};

export type MensagemCaso = {
  id: number;
  autor: 'advogado' | 'agente';
  texto: string;
  status: 'pendente' | 'concluida' | 'erro';
  erro: string;
  resultado: AgenteResultado | null;
  indice_atual: number | null;
  indice_potencial: number | null;
  // na mensagem do advogado: o que dos documentos do processo vinculado a análise leu
  documentos_lidos: { nome: string; situacao: string }[];
  criado_em: string;
};

export type CasoEstudo = {
  id: number;
  titulo: string;
  tema: string;
  fase: string;
  orgao_julgador: string;
  provas: string[];
  processo: number | null;
  mensagens: MensagemCaso[];
  etapa: string | null;
  criado_em: string;
  atualizado_em: string;
};

export type DadosDoCaso = Pick<CasoEstudo, 'fase' | 'orgao_julgador' | 'provas' | 'processo'>;

export type CasoEstudoResumo = Pick<CasoEstudo, 'id' | 'titulo' | 'tema' | 'fase' | 'atualizado_em'> & {
  indice_atual: number | null;
};

// Jurimetria do tribunal: sentenças públicas do TRT-16 (backend/juripredict/api/jurimetria_tribunal.py).
export type ResultadoTribunal = 'deferido' | 'indeferido';

export type TaxaTribunal = {
  total: number;
  suficiente: boolean;
  favoravel: number | null;
  desfavoravel: number | null;
  intervalo_favoravel: IntervaloPercentual | null;
  motivo: string | null;
  cobertura: number | null;
};

export type JurimetriaTribunalDisponivel = {
  disponivel: true;
  filtros: { tema: string; vara?: string; ano?: number };
  geral: TaxaTribunal;
  fora_da_taxa: Array<{ motivo: string; total: number }>;
  por_vara: Array<TaxaTribunal & { vara: string }>;
  por_ano: Array<TaxaTribunal & { ano: number }>;
  validacao: { rotulo_conferido: boolean; motivo: string | null; gold_set: Record<string, number> | null; cobertura_medida: boolean };
  opcoes: { temas: Array<{ valor: string; rotulo: string }>; varas: string[]; anos: number[] };
  fonte: { origem: string; inicio: string | null; fim: string | null; versao: string; importado_em: string };
  populacao: string;
  criterio: string;
  piso_amostra: number;
};

export type JurimetriaTribunal = JurimetriaTribunalDisponivel | { disponivel: false };

export type DecisoesTribunal = {
  total: number;
  exibidos: number;
  contagem: Partial<Record<ResultadoTribunal, number>>;
  decisoes: Array<{
    numero_cnj: string;
    vara: string;
    data_sentenca: string | null;
    resultado: ResultadoTribunal;
    grau: number | null;
    mecanismo: string;
    trecho: string;
  }>;
};
