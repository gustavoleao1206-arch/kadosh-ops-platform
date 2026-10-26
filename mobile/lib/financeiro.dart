/// Modelos do financeiro. Existem para o app parar de ler `Map<String, dynamic>` cru.
///
/// A tela do caixa nasceu lendo JSON na mão, e o preço foi este: nada avisa quando um campo muda
/// de nome no backend — o app só mostra um traço no lugar do número, e ninguém desconfia. Com
/// modelo tipado, o parse quebra alto e o teste pega.
///
/// Nenhuma conta aqui. Rótulo, cor e situação vêm prontos do servidor; estas classes só carregam.
library;

class Resumo {
  Resumo({required this.hoje, required this.mes, required this.cobranca});

  factory Resumo.doJson(Map<String, dynamic> j) => Resumo(
        hoje: ResumoHoje.doJson(j['hoje'] as Map<String, dynamic>),
        mes: ResumoMes.doJson(j['mes'] as Map<String, dynamic>),
        cobranca: ResumoCobranca.doJson(j['cobranca'] as Map<String, dynamic>),
      );

  final ResumoHoje hoje;
  final ResumoMes mes;
  final ResumoCobranca cobranca;
}

class ResumoHoje {
  ResumoHoje({
    required this.recebidoCentavos,
    required this.chegamQtd,
    required this.noPatioQtd,
    required this.orcamentosAbertosQtd,
  });

  factory ResumoHoje.doJson(Map<String, dynamic> j) => ResumoHoje(
        recebidoCentavos: j['recebido_centavos'] as int,
        chegamQtd: j['chegam_qtd'] as int,
        noPatioQtd: j['no_patio_qtd'] as int,
        orcamentosAbertosQtd: j['orcamentos_abertos_qtd'] as int,
      );

  final int recebidoCentavos;
  final int chegamQtd;
  final int noPatioQtd;
  final int orcamentosAbertosQtd;
}

class ResumoMes {
  ResumoMes({
    required this.label,
    required this.faturadoCentavos,
    required this.recebidoCentavos,
    required this.osConcluidas,
    required this.ticketMedioCentavos,
  });

  factory ResumoMes.doJson(Map<String, dynamic> j) => ResumoMes(
        // "Setembro de 2026" vem escrito do backend — o app não monta nome de mês
        label: j['label'] as String,
        faturadoCentavos: j['faturado_centavos'] as int,
        recebidoCentavos: j['recebido_centavos'] as int,
        osConcluidas: j['os_concluidas'] as int,
        ticketMedioCentavos: j['ticket_medio_centavos'] as int,
      );

  final String label;
  final int faturadoCentavos;
  final int recebidoCentavos;
  final int osConcluidas;
  final int ticketMedioCentavos;
}

class GrupoCobranca {
  GrupoCobranca({required this.qtd, required this.totalCentavos});

  factory GrupoCobranca.doJson(Map<String, dynamic> j) =>
      GrupoCobranca(qtd: j['qtd'] as int, totalCentavos: j['total_centavos'] as int);

  final int qtd;
  final int totalCentavos;
}

class ResumoCobranca {
  ResumoCobranca({required this.pendentes, required this.atrasados});

  factory ResumoCobranca.doJson(Map<String, dynamic> j) => ResumoCobranca(
        pendentes: GrupoCobranca.doJson(j['pendentes'] as Map<String, dynamic>),
        atrasados: GrupoCobranca.doJson(j['atrasados'] as Map<String, dynamic>),
      );

  final GrupoCobranca pendentes;
  final GrupoCobranca atrasados;
}

/// Um lançamento do caixa ou do extrato — as duas telas leem o MESMO formato, porque o backend
/// devolve o mesmo schema para as duas.
class Lancamento {
  Lancamento({
    required this.id,
    required this.workOrderId,
    required this.numero,
    required this.clienteNome,
    required this.valorCentavos,
    required this.formaLabel,
    required this.pagoEm,
    required this.estornadoEm,
    required this.estornoMotivo,
  });

  factory Lancamento.doJson(Map<String, dynamic> j) => Lancamento(
        id: j['id'] as int,
        workOrderId: j['work_order_id'] as int,
        numero: j['numero'] as int?,
        clienteNome: j['cliente_nome'] as String,
        valorCentavos: j['valor_centavos'] as int,
        formaLabel: j['forma_label'] as String,
        pagoEm: DateTime.parse(j['pago_em'] as String).toLocal(),
        estornadoEm: j['estornado_em'] == null
            ? null
            : DateTime.parse(j['estornado_em'] as String).toLocal(),
        estornoMotivo: j['estorno_motivo'] as String?,
      );

  final int id;
  final int workOrderId;
  final int? numero;
  final String clienteNome;
  final int valorCentavos;
  final String formaLabel;
  final DateTime pagoEm;
  final DateTime? estornadoEm;
  final String? estornoMotivo;

  bool get estornado => estornadoEm != null;

  String get numeroFormatado =>
      numero == null ? '#$workOrderId' : 'nº ${numero.toString().padLeft(3, '0')}';
}

class TotalPorForma {
  TotalPorForma({required this.formaLabel, required this.totalCentavos});

  factory TotalPorForma.doJson(Map<String, dynamic> j) => TotalPorForma(
        formaLabel: j['forma_label'] as String,
        totalCentavos: j['total_centavos'] as int,
      );

  final String formaLabel;
  final int totalCentavos;
}

/// O caixa esticado no tempo. Mesmo critério do dia: soma por quando o dinheiro entrou, e o
/// estornado aparece riscado mas fora do total.
class Extrato {
  Extrato({
    required this.periodoLabel,
    required this.totalCentavos,
    required this.estornosCentavos,
    required this.porForma,
    required this.lancamentos,
    required this.total,
  });

  factory Extrato.doJson(Map<String, dynamic> j) => Extrato(
        periodoLabel: (j['periodo'] as Map<String, dynamic>)['label'] as String,
        totalCentavos: j['total_centavos'] as int,
        estornosCentavos: j['estornos_centavos'] as int,
        porForma: ((j['por_forma'] as List?) ?? const [])
            .map((e) => TotalPorForma.doJson(e as Map<String, dynamic>))
            .toList(),
        lancamentos: ((j['lancamentos'] as List?) ?? const [])
            .map((e) => Lancamento.doJson(e as Map<String, dynamic>))
            .toList(),
        total: j['total'] as int,
      );

  final String periodoLabel;
  final int totalCentavos;
  final int estornosCentavos;
  final List<TotalPorForma> porForma;
  final List<Lancamento> lancamentos;
  final int total;
}

/// O caixa de um dia.
class Caixa {
  Caixa({
    required this.recebidoCentavos,
    required this.porForma,
    required this.lancamentos,
    required this.aReceberCentavos,
    required this.devedores,
  });

  factory Caixa.doJson(Map<String, dynamic> j) => Caixa(
        recebidoCentavos: j['recebido_centavos'] as int,
        porForma: ((j['por_forma'] as List?) ?? const [])
            .map((e) => TotalPorForma.doJson(e as Map<String, dynamic>))
            .toList(),
        lancamentos: ((j['lancamentos'] as List?) ?? const [])
            .map((e) => Lancamento.doJson(e as Map<String, dynamic>))
            .toList(),
        aReceberCentavos: j['a_receber_centavos'] as int,
        devedores: ((j['a_receber'] as List?) ?? const [])
            .map((e) => Devedor.doJson(e as Map<String, dynamic>))
            .toList(),
      );

  final int recebidoCentavos;
  final List<TotalPorForma> porForma;
  final List<Lancamento> lancamentos;
  final int aReceberCentavos;
  final List<Devedor> devedores;
}

class Devedor {
  Devedor({
    required this.workOrderId,
    required this.numero,
    required this.clienteNome,
    required this.saldoCentavos,
    required this.situacaoLabel,
    required this.situacaoTone,
    required this.vencimento,
  });

  factory Devedor.doJson(Map<String, dynamic> j) => Devedor(
        workOrderId: j['work_order_id'] as int,
        numero: j['numero'] as int?,
        clienteNome: j['cliente_nome'] as String,
        saldoCentavos: j['saldo_centavos'] as int,
        // a situação vem pronta: o app não sabe a regra do atraso, e é de propósito
        situacaoLabel: (j['situacao_cobranca_label'] ?? j['status_label']) as String?,
        situacaoTone: (j['situacao_cobranca_tone'] ?? j['status_tone']) as String?,
        vencimento: j['vencimento'] == null
            ? null
            : DateTime.parse(j['vencimento'] as String).toLocal(),
      );

  final int workOrderId;
  final int? numero;
  final String clienteNome;
  final int saldoCentavos;
  final String? situacaoLabel;
  final String? situacaoTone;
  final DateTime? vencimento;

  String get numeroFormatado =>
      numero == null ? '#$workOrderId' : 'nº ${numero.toString().padLeft(3, '0')}';
}

/// Relatório de um período.
///
/// O app mostra só o topo — os números que o sócio usa no balcão e os serviços que mais dão
/// dinheiro. O painel tem o resto (dia da semana, clientes sumidos, mês arbitrário): tela de
/// computador aguenta densidade que um celular no pátio não aguenta.
///
/// FATURADO e RECEBIDO são contas diferentes e nunca se somam — faturado é serviço entregue,
/// recebido é dinheiro que entrou. Quem paga o sinal num mês e leva o carro no outro cai nos dois
/// lados em meses diferentes. Por isso o faturado vem decomposto em "já entrou" e "falta".
class Relatorio {
  Relatorio({
    required this.periodoLabel,
    required this.temHistorico,
    required this.faturadoCentavos,
    required this.faturadoRecebidoCentavos,
    required this.faturadoAReceberCentavos,
    required this.recebidoCentavos,
    required this.osConcluidas,
    required this.ticketMedioCentavos,
    required this.descontoCentavos,
    required this.estornosCentavos,
    required this.cancelamentos,
    required this.naoComparecimentos,
    this.porForma = const <TotalPorForma>[],
    this.porServico = const [],
  });

  factory Relatorio.doJson(Map<String, dynamic> j) {
    final t = j['totais'] as Map<String, dynamic>;
    return Relatorio(
      periodoLabel: (j['periodo'] as Map<String, dynamic>)['label'] as String,
      temHistorico: (j['tem_historico'] as bool?) ?? true,
      faturadoCentavos: t['faturado_centavos'] as int,
      faturadoRecebidoCentavos: t['faturado_recebido_centavos'] as int,
      faturadoAReceberCentavos: t['faturado_a_receber_centavos'] as int,
      recebidoCentavos: t['recebido_centavos'] as int,
      osConcluidas: t['os_concluidas'] as int,
      ticketMedioCentavos: t['ticket_medio_centavos'] as int,
      descontoCentavos: t['desconto_centavos'] as int,
      estornosCentavos: (t['estornos_centavos'] as int?) ?? 0,
      cancelamentos: t['cancelamentos'] as int,
      naoComparecimentos: t['nao_comparecimentos'] as int,
      porForma: ((j['por_forma'] as List?) ?? const [])
          .map((f) => TotalPorForma.doJson(f as Map<String, dynamic>))
          .toList(),
      porServico: ((j['por_servico'] as List?) ?? const [])
          .map((s) => ServicoDoRelatorio.doJson(s as Map<String, dynamic>))
          .toList(),
    );
  }

  final String periodoLabel;

  /// false = a loja nunca concluiu OS nenhuma. Separa "loja nova" de "mês parado", que pedem
  /// mensagens diferentes: uma é expectativa, a outra é notícia ruim.
  final bool temHistorico;

  final int faturadoCentavos;
  final int faturadoRecebidoCentavos;
  final int faturadoAReceberCentavos;
  final int recebidoCentavos;
  final int osConcluidas;
  final int ticketMedioCentavos;
  final int descontoCentavos;
  final int estornosCentavos;
  final int cancelamentos;
  final int naoComparecimentos;
  final List<TotalPorForma> porForma;
  final List<ServicoDoRelatorio> porServico;

  bool get vazio => osConcluidas == 0 && recebidoCentavos == 0;
}

class ServicoDoRelatorio {
  ServicoDoRelatorio({required this.nome, required this.quantidade, required this.totalCentavos});

  factory ServicoDoRelatorio.doJson(Map<String, dynamic> j) => ServicoDoRelatorio(
        nome: j['nome'] as String,
        quantidade: j['quantidade'] as int,
        totalCentavos: j['total_centavos'] as int,
      );

  final String nome;
  final int quantidade;
  final int totalCentavos;
}

/// Um mês da série de evolução (`/relatorios/mensal`).
///
/// O rótulo vem pronto do servidor, curto e longo: "Set/26" cabe embaixo de uma barra, "Setembro
/// de 2026" não — e nenhum dos dois é montado aqui, porque nome de mês em português é do servidor
/// desde a fase 8 e ter duas tabelas de nomes é ter duas chances de discordarem.
class MesDoRelatorio {
  MesDoRelatorio({
    required this.mes,
    required this.label,
    required this.labelCurto,
    required this.faturadoCentavos,
    required this.recebidoCentavos,
    required this.osConcluidas,
  });

  factory MesDoRelatorio.doJson(Map<String, dynamic> j) => MesDoRelatorio(
        mes: j['mes'] as String,
        label: j['label'] as String,
        labelCurto: j['label_curto'] as String,
        faturadoCentavos: j['faturado_centavos'] as int,
        recebidoCentavos: j['recebido_centavos'] as int,
        osConcluidas: j['os_concluidas'] as int,
      );

  /// "2026-09" — a chave que volta para a API em `?periodo=mes_especifico&mes=`.
  final String mes;
  final String label;
  final String labelCurto;
  final int faturadoCentavos;
  final int recebidoCentavos;
  final int osConcluidas;
}
