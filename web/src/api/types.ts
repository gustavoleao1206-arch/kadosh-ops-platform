/** Tipos espelhando os schemas do backend (dinheiro sempre em centavos inteiros). */

export type Role = 'admin' | 'staff'

export interface User {
  id: number
  nome: string
  email: string
  role: Role
  is_active: boolean
  must_change_password: boolean
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface VehicleMini {
  id: number
  placa: string | null
  marca: string | null
  modelo: string
  cor: string | null
  ano: number | null
  descricao: string
  arquivado_em: string | null
}

export interface Client {
  id: number
  nome: string
  telefone: string | null
  email: string | null
  observacoes: string | null
  arquivado_em: string | null
  created_at: string
  updated_at: string
  veiculos: VehicleMini[]
}

export interface ClientStats {
  atendimentos: number
  total_gasto_centavos: number
  ultimo_atendimento: string | null
}

export interface WorkOrderSummary {
  id: number
  numero: number | null
  status: string
  status_label: string
  scheduled_at: string | null
  entrada: string | null
  conclusao: string | null
  valor_total_centavos: number
  vehicle_id: number | null
  veiculo: string | null
  client_id: number
  cliente: string
}

export interface ClientDetail extends Client {
  stats: ClientStats
  historico: WorkOrderSummary[]
}

export interface ClientMini {
  id: number
  nome: string
  telefone: string | null
  arquivado_em: string | null
}

export interface Vehicle {
  id: number
  client_id: number
  placa: string | null
  marca: string | null
  modelo: string
  cor: string | null
  ano: number | null
  observacoes: string | null
  descricao: string
  arquivado_em: string | null
  created_at: string
  updated_at: string
  cliente: ClientMini
}

export interface VehicleDetail extends Vehicle {
  historico: WorkOrderSummary[]
}

export interface SearchResult {
  q: string
  veiculos: Vehicle[]
  clientes: Client[]
}

export interface ClientInput {
  nome: string
  telefone?: string | null
  email?: string | null
  observacoes?: string | null
}

export interface VehicleInput {
  client_id: number
  placa?: string | null
  marca?: string | null
  modelo: string
  cor?: string | null
  ano?: number | null
  observacoes?: string | null
}

/* ---------- catálogo ---------- */

export interface Service {
  id: number
  nome: string
  descricao: string | null
  valor_base_centavos: number
  duracao_estimada_min: number
  ativo: boolean
  created_at: string
  updated_at: string
  /**
   * Só vêm preenchidos quando a lista foi pedida com `client_id`. É o que deixa o seletor de
   * serviço da OS já vir com o preço certo — e, principalmente, dizer DE ONDE ele veio: sem o
   * rótulo de origem, um preço combinado parece erro do sistema.
   */
  valor_cliente_centavos?: number | null
  valor_efetivo_centavos?: number | null
}

/* ---------- ordens de serviço ---------- */

export type Tone = 'neutral' | 'gold' | 'ok' | 'warn' | 'danger'

export interface WorkOrderItem {
  id: number
  service_id: number
  descricao: string
  valor_centavos: number
  created_at: string
}

export interface WorkOrderEvent {
  id: number
  tipo: string
  /** frase pronta em português, montada pelo backend */
  descricao: string
  de: string | null
  para: string | null
  motivo: string | null
  user_id: number | null
  created_at: string
}

export interface Transition {
  status: string
  label: string
  /** verbo para o botão ("Confirmar"), diferente do rótulo do estado ("Confirmado") */
  acao_label: string
  tone: Tone
  requer_motivo: boolean
  /** o passo esperado agora — o único botão em destaque */
  principal: boolean
}

export interface WorkOrder {
  id: number
  numero: number | null
  /** true = previsão digitada à mão; o backend para de recalculá-la */
  previsao_manual: boolean
  status: string
  status_label: string
  status_tone: Tone
  client_id: number
  vehicle_id: number | null
  scheduled_at: string | null
  entrada: string | null
  previsao_conclusao: string | null
  conclusao: string | null
  /** data-limite combinada para receber; null na maioria das OS (paga-se na retirada) */
  vencimento: string | null
  desconto_centavos: number
  valor_total_centavos: number
  /** já recebido (pagamentos não estornados) — vem pronto do backend */
  pago_centavos: number
  /** o que falta receber; nunca negativo */
  saldo_centavos: number
  /**
   * A régua de cobrança pronta: pago / a receber / atrasado, com rótulo e cor.
   * null quando esta OS não é cobrança (orçamento, cancelada, total zero).
   * O painel NÃO recalcula: a data de corte do atraso é do servidor.
   */
  situacao_cobranca: SituacaoCobranca | null
  situacao_cobranca_label: string | null
  situacao_cobranca_tone: Tone | null
  observacoes: string | null
  observacoes_entrada: string | null
  created_at: string
  updated_at: string
  itens: WorkOrderItem[]
  cliente: Client
  veiculo: Vehicle | null
}

export type SituacaoCobranca = 'pago' | 'pendente' | 'atrasado'

export interface WorkOrderDetail extends WorkOrder {
  eventos: WorkOrderEvent[]
  acoes: Transition[]
  pagamentos: Payment[]
  aceita_pagamento: boolean
}

export interface Payment {
  id: number
  valor_centavos: number
  forma: string
  forma_label: string
  pago_em: string
  created_at: string
  observacao: string | null
  estornado_em: string | null
  estorno_motivo: string | null
  created_by: number | null
  /** a regra de quem estorna mora no backend; aqui só se desenha */
  pode_estornar: boolean
}

export interface FormaPagamento {
  valor: string
  label: string
}

export interface Caixa {
  dia: string
  recebido_centavos: number
  por_forma: { forma: string; forma_label: string; total_centavos: number }[]
  lancamentos: CaixaLancamento[]
  a_receber_centavos: number
  a_receber: CaixaDevedor[]
}

export interface CaixaLancamento {
  id: number
  work_order_id: number
  numero: number | null
  cliente_nome: string
  valor_centavos: number
  forma: string
  forma_label: string
  pago_em: string
  created_at: string
  observacao: string | null
  estornado_em: string | null
  estorno_motivo: string | null
}

export interface CaixaDevedor {
  work_order_id: number
  numero: number | null
  cliente_nome: string
  status: string
  status_label: string
  status_tone: Tone
  valor_total_centavos: number
  pago_centavos: number
  saldo_centavos: number
  situacao_cobranca: SituacaoCobranca | null
  situacao_cobranca_label: string | null
  situacao_cobranca_tone: Tone | null
  vencimento: string | null
}

export interface AgendaResumo {
  agendados: number
  confirmados: number
  no_patio: number
  orcamentos_abertos: number
}

export interface Agenda {
  dia: string
  resumo: AgendaResumo
  itens: WorkOrder[]
}

export interface Relatorio {
  periodo: { chave: string; de: string; ate: string; label: string }
  /** false = a loja ainda não concluiu nenhuma OS na vida (vazio diferente de "mês parado") */
  tem_historico: boolean
  totais: {
    /** o serviço entregue no período */
    faturado_centavos: number
    /** ...e quanto dele já entrou / ainda falta. As duas partes fecham com o faturado. */
    faturado_recebido_centavos: number
    faturado_a_receber_centavos: number
    /** o dinheiro que entrou no período, venha da OS que vier */
    recebido_centavos: number
    os_concluidas: number
    ticket_medio_centavos: number
    desconto_centavos: number
    cancelamentos: number
    nao_comparecimentos: number
    /** o que foi estornado dentro da janela — a linha que faz a conferência manual fechar */
    estornos_centavos: number
  }
  /** de onde veio o dinheiro do período: a mesma quebra do caixa e do extrato */
  por_forma: FormaLinha[]
  por_servico: { service_id: number; nome: string; quantidade: number; total_centavos: number }[]
  por_dia_semana: { dia: number; dia_label: string; os_concluidas: number; faturado_centavos: number }[]
}

export interface ClientesSumidos {
  /** total antes do corte da lista — a tela avisa quando há mais do que cabe */
  total: number
  itens: ClienteSumido[]
}

export interface ClienteSumido {
  client_id: number
  nome: string
  telefone: string | null
  atendimentos: number
  total_gasto_centavos: number
  ultimo_atendimento: string
  dias_sem_voltar: number
}


export interface FormaLinha {
  forma: string
  forma_label: string
  total_centavos: number
}

/** O caixa esticado no tempo: mesmo critério de soma, estornado aparece riscado e fora do total. */
export interface Extrato {
  periodo: { de: string; ate: string; label: string }
  total_centavos: number
  estornos_centavos: number
  por_forma: FormaLinha[]
  lancamentos: CaixaLancamento[]
  /** todos os lançamentos da janela, inclusive os estornados listados */
  total: number
  page: number
  page_size: number
}

export interface MesLinha {
  mes: string
  label: string
  /** "Set/26" — o eixo do gráfico não comporta "Setembro de 2026" */
  label_curto: string
  faturado_centavos: number
  recebido_centavos: number
  os_concluidas: number
}

export interface SerieMensal {
  meses: MesLinha[]
}

export interface CobrancaGrupo {
  qtd: number
  total_centavos: number
}

/** A primeira tela. Nenhum número nasce aqui: tudo vem dos mesmos serviços do caixa e do relatório. */
export interface Dashboard {
  hoje: {
    dia: string
    recebido_centavos: number
    chegam_qtd: number
    no_patio_qtd: number
    orcamentos_abertos_qtd: number
  }
  mes: {
    label: string
    faturado_centavos: number
    recebido_centavos: number
    os_concluidas: number
    ticket_medio_centavos: number
    /** para a seta de comparação — quem calcula a variação é a tela, com os dois números na mão */
    mes_anterior: { faturado_centavos: number; recebido_centavos: number }
  }
  cobranca: {
    pendentes: CobrancaGrupo
    atrasados: CobrancaGrupo
  }
}

/** O catálogo visto por um cliente: preço de tabela, o dele, e o que vale de fato. */
export interface PrecoCliente {
  service_id: number
  servico_nome: string
  valor_base_centavos: number
  /** null = sem combinado; paga a tabela */
  valor_cliente_centavos: number | null
  valor_efetivo_centavos: number
  /** false só aparece em serviço desativado que AINDA tem combinado — para poder ser removido */
  ativo: boolean
}
