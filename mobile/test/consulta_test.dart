import 'package:flutter_test/flutter_test.dart';
import 'package:kadosh_campo/financeiro.dart';
import 'package:kadosh_campo/modelos.dart';

/// As telas de consulta (agenda, clientes, catálogo, relatórios) não calculam nada: elas leem o
/// payload e desenham. O que pode quebrar, então, é a LEITURA — um campo com nome errado some sem
/// estourar exceção nenhuma, e a tela fica com um buraco que parece dado faltando no banco.
///
/// Por isso cada teste aqui usa a chave exata que o backend manda (`scheduled_at`, não
/// `agendado_para`; `duracao_estimada_min`, não `duracao_min`).
void main() {
  group('OS.doJson: os campos que a agenda precisa', () {
    Map<String, dynamic> os({String? agendado, String? entrada}) => {
          'id': 3,
          'numero': 12,
          'status': 'agendado',
          'status_label': 'Agendado',
          'status_tone': 'muted',
          'cliente': {'nome': 'Ruan', 'telefone': '5582999110001'},
          'veiculo': {'placa': 'BRA2E19', 'marca': 'Honda', 'modelo': 'Civic'},
          'itens': const [],
          'acoes': const [],
          'valor_total_centavos': 0,
          'pago_centavos': 0,
          'saldo_centavos': 0,
          'previsao_conclusao': null,
          'scheduled_at': agendado,
          'entrada': entrada,
        };

    test('lê scheduled_at e entrada — as duas horas que a linha da agenda mostra', () {
      final o = OS.doJson(os(agendado: '2026-09-11T13:00:00+00:00', entrada: '2026-09-11T14:30:00+00:00'));
      expect(hora(o.agendadoPara), '10:00'); // 13:00 UTC = 10:00 em Maceió
      expect(hora(o.entrada), '11:30');
    });

    test('OS que nunca foi marcada nem chegou fica com os dois nulos, não com uma data inventada', () {
      final o = OS.doJson(os());
      expect(o.agendadoPara, isNull);
      expect(o.entrada, isNull);
    });

    test('o pátio manda payload sem essas chaves e isso não pode quebrar a leitura', () {
      final j = os()..remove('scheduled_at');
      j.remove('entrada');
      expect(OS.doJson(j).agendadoPara, isNull);
    });
  });

  group('telefoneFormatado: mesma régua do painel', () {
    // Os casos são os mesmos de `web/src/lib/format.ts`. Se um dia divergirem, o mesmo telefone
    // aparece escrito de dois jeitos — no painel e no celular — e alguém vai achar que são dois
    // cadastros diferentes.
    test('celular brasileiro de 9 dígitos', () {
      expect(telefoneFormatado('5582999110001'), '(82) 99911-0001');
    });

    test('fixo brasileiro de 8 dígitos', () {
      expect(telefoneFormatado('558233110001'), '(82) 3311-0001');
    });

    test('número de fora sai como veio, com "+" — máscara chutada é pior que nenhuma', () {
      expect(telefoneFormatado('12125550100'), '+12125550100');
    });

    test('sem telefone vira travessão, não string vazia que some na tela', () {
      expect(telefoneFormatado(null), '—');
      expect(telefoneFormatado(''), '—');
    });
  });

  group('dataCompleta: histórico precisa do ano', () {
    test('escreve dia/mês/ano curto no fuso da loja', () {
      expect(dataCompleta(DateTime.utc(2026, 9, 25, 12)), '25/09/26');
    });

    test('a virada do ano é lida na hora da LOJA, não na do aparelho', () {
      // 1º de janeiro de 2027 às 01:00 UTC ainda é 31 de dezembro de 2026 em Maceió.
      expect(dataCompleta(DateTime.utc(2027, 1, 1, 1)), '31/12/26');
    });
  });

  group('Cliente e ficha', () {
    final ficha = {
      'id': 9,
      'nome': 'Maria Souza',
      'telefone': '5582988887777',
      'email': null,
      'arquivado_em': null,
      'veiculos': [
        {'id': 1, 'placa': 'ABC1D23', 'marca': 'Toyota', 'modelo': 'Corolla'},
        {'id': 2, 'placa': null, 'marca': null, 'modelo': 'Gol'},
      ],
      'stats': {
        'atendimentos': 4,
        'total_gasto_centavos': 86000,
        'ultimo_atendimento': '2026-08-30T15:00:00+00:00',
      },
      'historico': [
        {
          'id': 55,
          'numero': 5,
          'status_label': 'Concluída',
          'valor_total_centavos': 36660,
          'veiculo': 'Toyota Corolla',
          'conclusao': '2026-08-30T15:00:00+00:00',
        },
      ],
    };

    test('lê os números da relação com a loja', () {
      final f = ClienteFicha.doJson(ficha);
      expect(f.cliente.nome, 'Maria Souza');
      expect(f.atendimentos, 4);
      expect(f.totalGastoCentavos, 86000);
      expect(f.historico.single.numeroFormatado, 'nº 005');
    });

    test('veículo sem marca não vira " Gol" com espaço na frente', () {
      final f = ClienteFicha.doJson(ficha);
      expect(f.cliente.veiculos[0].descricao, 'Toyota Corolla');
      expect(f.cliente.veiculos[1].descricao, 'Gol');
    });

    test('cliente sem atendimento nenhum: a ficha abre zerada em vez de estourar', () {
      final f = ClienteFicha.doJson({
        'id': 1,
        'nome': 'Novo',
        'telefone': null,
        'arquivado_em': null,
      });
      expect(f.atendimentos, 0);
      expect(f.ultimoAtendimento, isNull);
      expect(f.historico, isEmpty);
      expect(f.cliente.veiculos, isEmpty);
    });

    test('arquivado é derivado da data, não de um booleano que o backend não manda', () {
      expect(Cliente.doJson({'id': 1, 'nome': 'X', 'arquivado_em': '2026-01-01T00:00:00+00:00'}).arquivado, isTrue);
      expect(Cliente.doJson({'id': 1, 'nome': 'X', 'arquivado_em': null}).arquivado, isFalse);
    });
  });

  group('OSResumo.quando: qual data a linha do histórico mostra', () {
    OSResumo resumo({String? conclusao, String? entrada, String? agendado}) => OSResumo.doJson({
          'id': 1,
          'status_label': 'Concluída',
          'valor_total_centavos': 100,
          'conclusao': conclusao,
          'entrada': entrada,
          'scheduled_at': agendado,
        });

    test('OS entregue mostra a saída — é a data que o cliente lembra', () {
      final r = resumo(conclusao: '2026-09-10T12:00:00+00:00', entrada: '2026-09-09T12:00:00+00:00');
      expect(dataCompleta(r.quando!), '10/09/26');
    });

    test('carro que entrou e ainda não saiu mostra a entrada', () {
      final r = resumo(entrada: '2026-09-09T12:00:00+00:00', agendado: '2026-09-08T12:00:00+00:00');
      expect(dataCompleta(r.quando!), '09/09/26');
    });

    test('só marcado, sem ter chegado, mostra o agendamento', () {
      final r = resumo(agendado: '2026-09-08T12:00:00+00:00');
      expect(dataCompleta(r.quando!), '08/09/26');
    });

    test('sem nenhuma das três a linha fica sem data, e não com a de hoje', () {
      expect(resumo().quando, isNull);
    });
  });

  group('Servico: o catálogo lê três campos que o seletor de OS ignora', () {
    test('lê descrição, duração e ativo com as chaves do backend', () {
      final s = Servico.doJson({
        'id': 2,
        'nome': 'Vitrificação',
        'valor_base_centavos': 120000,
        'descricao': 'Proteção cerâmica com durabilidade de 12 meses.',
        'duracao_estimada_min': 480,
        'ativo': false,
      });
      expect(s.duracaoMin, 480);
      expect(s.ativo, isFalse);
      expect(s.descricao, startsWith('Proteção cerâmica'));
    });

    test('payload antigo (só id, nome e preço) continua válido e nasce ativo', () {
      final s = Servico.doJson({'id': 1, 'nome': 'Lavagem', 'valor_base_centavos': 8000});
      expect(s.ativo, isTrue);
      expect(s.duracaoMin, 0);
      expect(s.descricao, isNull);
    });
  });

  group('Relatorio', () {
    final payload = {
      'periodo': {'chave': 'mes', 'de': '2026-09-01', 'ate': '2026-09-30', 'label': 'Setembro de 2026'},
      'tem_historico': true,
      'totais': {
        'faturado_centavos': 500000,
        'faturado_recebido_centavos': 350000,
        'faturado_a_receber_centavos': 150000,
        'recebido_centavos': 380000,
        'os_concluidas': 14,
        'ticket_medio_centavos': 35714,
        'desconto_centavos': 12000,
        'cancelamentos': 1,
        'nao_comparecimentos': 2,
        'estornos_centavos': 5000,
      },
      'por_forma': [
        {'forma': 'pix', 'forma_label': 'Pix', 'total_centavos': 300000},
      ],
      'por_servico': [
        {'service_id': 1, 'nome': 'Polimento', 'quantidade': 6, 'total_centavos': 200000},
      ],
      'por_dia_semana': const [],
    };

    test('lê os totais e as duas quebras que o app mostra', () {
      final r = Relatorio.doJson(payload);
      expect(r.periodoLabel, 'Setembro de 2026');
      expect(r.faturadoCentavos, 500000);
      expect(r.porForma.single.formaLabel, 'Pix');
      expect(r.porServico.single.quantidade, 6);
    });

    test('as duas partes do faturado fecham com ele — é o que o bloco da tela afirma', () {
      final r = Relatorio.doJson(payload);
      expect(r.faturadoRecebidoCentavos + r.faturadoAReceberCentavos, r.faturadoCentavos);
    });

    test('recebido NÃO é uma parte do faturado: são contas diferentes e podem divergir', () {
      final r = Relatorio.doJson(payload);
      // 380.000 recebidos contra 350.000 do que foi faturado no mês: a diferença é dinheiro de OS
      // de outro mês. Se um dia alguém "consertar" isso somando, este teste cai.
      expect(r.recebidoCentavos, isNot(r.faturadoRecebidoCentavos));
    });

    test('loja sem histórico é diferente de mês parado', () {
      final novo = Map<String, dynamic>.from(payload)..['tem_historico'] = false;
      expect(Relatorio.doJson(novo).temHistorico, isFalse);
    });
  });

  group('MesDoRelatorio: o rótulo vem pronto do servidor', () {
    test('guarda a chave que volta para a API e os dois rótulos', () {
      final m = MesDoRelatorio.doJson({
        'mes': '2026-08',
        'label': 'Agosto de 2026',
        'label_curto': 'Ago/26',
        'faturado_centavos': 410000,
        'recebido_centavos': 400000,
        'os_concluidas': 11,
      });
      expect(m.mes, '2026-08');
      expect(m.labelCurto, 'Ago/26');
      // A barra do gráfico escreve só o mês; o ano fica no rótulo do relatório em cima.
      expect(m.labelCurto.split('/').first, 'Ago');
    });
  });
}
