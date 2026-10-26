/// Espelhos dos payloads da API. Sem regra de negócio aqui: rótulo, cor e o que dá para fazer com
/// cada OS vêm prontos do backend — o app só desenha o que recebe.
library;

class Acao {
  Acao(this.status, this.label, this.acaoLabel, this.tone, this.requerMotivo, this.principal);

  factory Acao.doJson(Map<String, dynamic> j) => Acao(
        j['status'] as String,
        j['label'] as String,
        j['acao_label'] as String,
        j['tone'] as String,
        j['requer_motivo'] as bool,
        j['principal'] as bool,
      );

  final String status;
  final String label;

  /// O verbo do botão ("Iniciar execução"), diferente do rótulo do estado ("Em execução").
  final String acaoLabel;
  final String tone;
  final bool requerMotivo;

  /// O passo esperado agora — o único que ganha destaque na tela.
  final bool principal;
}

class Item {
  Item(this.id, this.descricao, this.valorCentavos);

  factory Item.doJson(Map<String, dynamic> j) =>
      Item(j['id'] as int, j['descricao'] as String, j['valor_centavos'] as int);

  final int id;
  final String descricao;
  final int valorCentavos;
}

class OS {
  OS({
    required this.id,
    required this.numero,
    required this.status,
    required this.statusLabel,
    required this.statusTone,
    required this.clienteNome,
    required this.clienteTelefone,
    required this.placa,
    required this.veiculo,
    required this.itens,
    required this.acoes,
    this.descontoCentavos = 0,
    required this.valorTotalCentavos,
    required this.pagoCentavos,
    required this.saldoCentavos,
    required this.aceitaPagamento,
    this.situacaoCobranca,
    this.situacaoCobrancaLabel,
    this.situacaoCobrancaTone,
    this.vencimento,
    required this.previsaoConclusao,
    required this.pagamentos,
    required this.observacoesEntrada,
    this.agendadoPara,
    this.entrada,
  });

  factory OS.doJson(Map<String, dynamic> j) {
    final cliente = j['cliente'] as Map<String, dynamic>;
    final veiculo = j['veiculo'] as Map<String, dynamic>?;
    final marca = veiculo?['marca'] as String?;
    final modelo = veiculo?['modelo'] as String?;
    return OS(
      id: j['id'] as int,
      numero: j['numero'] as int?,
      status: j['status'] as String,
      statusLabel: j['status_label'] as String,
      statusTone: j['status_tone'] as String,
      clienteNome: cliente['nome'] as String,
      clienteTelefone: cliente['telefone'] as String?,
      placa: veiculo?['placa'] as String?,
      veiculo: [?marca, ?modelo].join(' '),
      itens: ((j['itens'] as List?) ?? const [])
          .map((e) => Item.doJson(e as Map<String, dynamic>))
          .toList(),
      acoes: ((j['acoes'] as List?) ?? const [])
          .map((e) => Acao.doJson(e as Map<String, dynamic>))
          .toList(),
      descontoCentavos: (j['desconto_centavos'] as int?) ?? 0,
      valorTotalCentavos: j['valor_total_centavos'] as int,
      pagoCentavos: j['pago_centavos'] as int,
      saldoCentavos: j['saldo_centavos'] as int,
      // só o detalhe traz estes três; na lista o pátio não precisa deles
      aceitaPagamento: (j['aceita_pagamento'] as bool?) ?? false,
      situacaoCobranca: j['situacao_cobranca'] as String?,
      situacaoCobrancaLabel: j['situacao_cobranca_label'] as String?,
      situacaoCobrancaTone: j['situacao_cobranca_tone'] as String?,
      vencimento: j['vencimento'] == null
          ? null
          : DateTime.parse(j['vencimento'] as String).toLocal(),
      pagamentos: ((j['pagamentos'] as List?) ?? const [])
          .map((e) => Pagamento.doJson(e as Map<String, dynamic>))
          .toList(),
      observacoesEntrada: j['observacoes_entrada'] as String?,
      previsaoConclusao: j['previsao_conclusao'] == null
          ? null
          : DateTime.parse(j['previsao_conclusao'] as String).toLocal(),
      // A agenda precisa destes dois; o pátio nunca precisou, e por isso eles não existiam aqui.
      agendadoPara: j['scheduled_at'] == null
          ? null
          : DateTime.parse(j['scheduled_at'] as String).toLocal(),
      entrada: j['entrada'] == null ? null : DateTime.parse(j['entrada'] as String).toLocal(),
    );
  }

  final int id;
  final int? numero;
  final String status;
  final String statusLabel;
  final String statusTone;
  final String clienteNome;
  final String? clienteTelefone;
  final String? placa;
  final String veiculo;
  final List<Item> itens;
  final List<Acao> acoes;
  final int descontoCentavos;
  final int valorTotalCentavos;
  final int pagoCentavos;
  final int saldoCentavos;
  final bool aceitaPagamento;
  /// A régua de cobrança pronta: pago / pendente / atrasado — ou null quando esta OS não é
  /// cobrança. O app NÃO recalcula: a data de corte do atraso é do servidor, e um celular com o
  /// relógio errado inventaria atraso que não existe.
  final String? situacaoCobranca;
  final String? situacaoCobrancaLabel;
  final String? situacaoCobrancaTone;
  final DateTime? vencimento;
  final DateTime? previsaoConclusao;
  /// Hora marcada (agenda) e hora em que o carro chegou (pátio). A agenda mostra uma ou outra.
  final DateTime? agendadoPara;
  final DateTime? entrada;
  final List<Pagamento> pagamentos;
  final String? observacoesEntrada;

  String get numeroFormatado =>
      numero == null ? '#$id' : 'nº ${numero.toString().padLeft(3, '0')}';

  /// Passou da hora prometida e ainda não está pronto. Mesma regra do painel.
  bool get atrasado =>
      previsaoConclusao != null &&
      previsaoConclusao!.isBefore(DateTime.now()) &&
      status != 'aguardando_retirada';

  Acao? get acaoPrincipal {
    for (final a in acoes) {
      if (a.principal) return a;
    }
    return null;
  }
}

class Pagamento {
  Pagamento(
    this.id,
    this.valorCentavos,
    this.formaLabel,
    this.pagoEm,
    this.estornadoEm,
    this.podeEstornar,
  );

  factory Pagamento.doJson(Map<String, dynamic> j) => Pagamento(
        j['id'] as int,
        j['valor_centavos'] as int,
        j['forma_label'] as String,
        DateTime.parse(j['pago_em'] as String).toLocal(),
        j['estornado_em'] == null
            ? null
            : DateTime.parse(j['estornado_em'] as String).toLocal(),
        (j['pode_estornar'] as bool?) ?? false,
      );

  final int id;
  final int valorCentavos;
  final String formaLabel;
  final DateTime pagoEm;

  /// Estornado continua na lista: o rastro é o produto. Só não conta no total.
  final DateTime? estornadoEm;

  /// Calculado pelo backend por usuário: quem lançou desfaz o próprio, o resto é do administrador.
  /// O app não reimplementa isso — só desenha o botão quando vem `true`.
  final bool podeEstornar;

  bool get estornado => estornadoEm != null;
}

class FormaPagamento {
  FormaPagamento(this.valor, this.label);

  factory FormaPagamento.doJson(Map<String, dynamic> j) =>
      FormaPagamento(j['valor'] as String, j['label'] as String);

  final String valor;
  final String label;
}

class Servico {
  Servico(this.id, this.nome, this.valorBaseCentavos, {this.descricao, this.duracaoMin = 0, this.ativo = true});

  factory Servico.doJson(Map<String, dynamic> j) => Servico(
        j['id'] as int,
        j['nome'] as String,
        j['valor_base_centavos'] as int,
        descricao: j['descricao'] as String?,
        duracaoMin: (j['duracao_estimada_min'] as int?) ?? 0,
        ativo: (j['ativo'] as bool?) ?? true,
      );

  final int id;
  final String nome;
  final int valorBaseCentavos;
  // Só a tela de consulta de preços usa os três abaixo; o seletor da OS ignora.
  final String? descricao;
  final int duracaoMin;
  final bool ativo;
}

/// Cliente como a lista e a ficha mostram.
///
/// O app NÃO cadastra nem edita cliente: quem cria é a recepção (que já monta cliente, veículo e
/// OS numa transação só) e quem corrige é o painel. Aqui é consulta — achar o telefone, ver o que
/// a pessoa já fez na loja e ligar para ela.
class Cliente {
  Cliente({
    required this.id,
    required this.nome,
    this.telefone,
    this.email,
    this.veiculos = const [],
    this.arquivado = false,
  });

  factory Cliente.doJson(Map<String, dynamic> j) => Cliente(
        id: j['id'] as int,
        nome: j['nome'] as String,
        telefone: j['telefone'] as String?,
        email: j['email'] as String?,
        arquivado: j['arquivado_em'] != null,
        veiculos: ((j['veiculos'] as List?) ?? const [])
            .map((v) => VeiculoResumo.doJson(v as Map<String, dynamic>))
            .toList(),
      );

  final int id;
  final String nome;
  final String? telefone;
  final String? email;
  final List<VeiculoResumo> veiculos;
  final bool arquivado;
}

class VeiculoResumo {
  VeiculoResumo({required this.id, required this.modelo, this.marca, this.placa});

  factory VeiculoResumo.doJson(Map<String, dynamic> j) => VeiculoResumo(
        id: j['id'] as int,
        modelo: (j['modelo'] as String?) ?? '',
        marca: j['marca'] as String?,
        placa: j['placa'] as String?,
      );

  final int id;
  final String modelo;
  final String? marca;
  final String? placa;

  String get descricao => [if (marca != null && marca!.isNotEmpty) marca, modelo].join(' ').trim();
}

/// Ficha do cliente: os números da relação dele com a loja e o histórico de OS.
class ClienteFicha {
  ClienteFicha({
    required this.cliente,
    required this.atendimentos,
    required this.totalGastoCentavos,
    this.ultimoAtendimento,
    this.historico = const [],
  });

  factory ClienteFicha.doJson(Map<String, dynamic> j) {
    final s = (j['stats'] as Map<String, dynamic>?) ?? const {};
    return ClienteFicha(
      cliente: Cliente.doJson(j),
      atendimentos: (s['atendimentos'] as int?) ?? 0,
      totalGastoCentavos: (s['total_gasto_centavos'] as int?) ?? 0,
      ultimoAtendimento: s['ultimo_atendimento'] == null
          ? null
          : DateTime.parse(s['ultimo_atendimento'] as String),
      historico: ((j['historico'] as List?) ?? const [])
          .map((h) => OSResumo.doJson(h as Map<String, dynamic>))
          .toList(),
    );
  }

  final Cliente cliente;
  final int atendimentos;
  final int totalGastoCentavos;
  final DateTime? ultimoAtendimento;
  final List<OSResumo> historico;
}

/// OS em lista de histórico. É o `WorkOrderSummaryOut` do backend — bem menor que a OS completa,
/// e de propósito: a ficha do cliente não precisa de itens, eventos nem pagamentos.
class OSResumo {
  OSResumo({
    required this.id,
    required this.statusLabel,
    required this.valorTotalCentavos,
    this.numero,
    this.veiculo,
    this.conclusao,
    this.entrada,
    this.agendadoPara,
  });

  factory OSResumo.doJson(Map<String, dynamic> j) => OSResumo(
        id: j['id'] as int,
        numero: j['numero'] as int?,
        statusLabel: (j['status_label'] as String?) ?? '',
        valorTotalCentavos: (j['valor_total_centavos'] as int?) ?? 0,
        veiculo: j['veiculo'] as String?,
        conclusao: j['conclusao'] == null ? null : DateTime.parse(j['conclusao'] as String),
        entrada: j['entrada'] == null ? null : DateTime.parse(j['entrada'] as String),
        agendadoPara: j['scheduled_at'] == null ? null : DateTime.parse(j['scheduled_at'] as String),
      );

  final int id;
  final int? numero;
  final String statusLabel;
  final int valorTotalCentavos;
  final String? veiculo;
  final DateTime? conclusao;
  final DateTime? entrada;
  final DateTime? agendadoPara;

  /// A data que importa para esta linha: quando saiu, quando entrou, ou quando está marcada.
  DateTime? get quando => conclusao ?? entrada ?? agendadoPara;

  String get numeroFormatado => numero == null ? '#$id' : 'nº ${numero.toString().padLeft(3, '0')}';
}

/// 12990 -> "R$ 129,90". O backend manda centavos inteiros; formatar é trabalho de tela.
String reais(int centavos) {
  final s = (centavos / 100).toStringAsFixed(2).replaceAll('.', ',');
  final partes = s.split(',');
  final inteiro = partes[0].replaceAllMapped(
    RegExp(r'(\d)(?=(\d{3})+$)'),
    (m) => '${m[1]}.',
  );
  return 'R\$ $inteiro,${partes[1]}';
}

/// "BRA2E19" -> "BRA-2E19", como o balcão lê.
String placaFormatada(String? placa) {
  if (placa == null || placa.isEmpty) return '—';
  if (placa.length == 7) return '${placa.substring(0, 3)}-${placa.substring(3)}';
  return placa;
}

/// Primeiro nome, como o painel escreve nas mensagens de WhatsApp.
String primeiroNome(String nome) {
  final partes = nome.trim().split(RegExp(r'\s+'));
  return partes.isEmpty ? nome : partes.first;
}

/// A hora e a data que o app mostra são as da LOJA, não as do aparelho.
///
/// O painel já decide assim (`format.ts` fixa America/Maceio) e o app precisa concordar: os dois
/// leem os mesmos números, e "vence dia 25" não pode virar 26 porque o celular está com outro fuso
/// — um vencimento é gravado às 23:59 em Maceió, então bastam alguns minutos de diferença para o
/// dia virar.
///
/// O deslocamento é fixo em −3h de propósito, em vez de trazer o pacote `timezone` (uma base de
/// fusos inteira dentro do APK): Maceió é UTC−3 o ano todo. O Brasil acabou com o horário de verão
/// em 2019 e, mesmo antes disso, os estados do Nordeste nunca o adotaram. Se um dia voltar, este é
/// o ponto único a mudar.
const _fusoDaLoja = Duration(hours: -3);

DateTime noFusoDaLoja(DateTime d) => d.toUtc().add(_fusoDaLoja);

String hora(DateTime? d) {
  if (d == null) return '';
  final loja = noFusoDaLoja(d);
  return '${loja.hour.toString().padLeft(2, '0')}:${loja.minute.toString().padLeft(2, '0')}';
}

/// "25/09" — dia e mês, que é o que cabe e o que basta numa linha de cobrança.
String data(DateTime d) {
  final loja = noFusoDaLoja(d);
  return '${loja.day.toString().padLeft(2, '0')}/${loja.month.toString().padLeft(2, '0')}';
}

/// "25/09/26" — quando a linha é histórico e o ano deixa de ser óbvio.
String dataCompleta(DateTime d) {
  final loja = noFusoDaLoja(d);
  final ano = (loja.year % 100).toString().padLeft(2, '0');
  return '${data(d)}/$ano';
}

/// "5582999110001" -> "(82) 99911-0001". Mesma regra do painel (`web/src/lib/format.ts`), para o
/// mesmo telefone não aparecer escrito de dois jeitos nas duas telas.
///
/// O backend guarda só dígitos com DDI. Número que não seja brasileiro sai como veio, com "+":
/// inventar máscara para um formato desconhecido é pior do que não mascarar.
String telefoneFormatado(String? digitos) {
  if (digitos == null || digitos.isEmpty) return '—';
  if (digitos.startsWith('55') && (digitos.length == 12 || digitos.length == 13)) {
    final ddd = digitos.substring(2, 4);
    final resto = digitos.substring(4);
    final corte = resto.length == 9 ? 5 : 4;
    return '($ddd) ${resto.substring(0, corte)}-${resto.substring(corte)}';
  }
  return '+$digitos';
}
