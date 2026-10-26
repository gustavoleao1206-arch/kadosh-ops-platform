/// Parse do financeiro contra o JSON REAL da API.
///
/// O motivo destes testes é concreto: a tela do caixa nasceu lendo `Map<String, dynamic>` na mão, e
/// quando um campo muda de nome no backend nada avisa — o app só mostra um traço no lugar do
/// número, e ninguém desconfia. Os payloads abaixo são cópias do que o servidor devolve.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:kadosh_campo/api.dart';
import 'package:kadosh_campo/financeiro.dart';
import 'package:kadosh_campo/modelos.dart';

void main() {
  group('Resumo (/dashboard)', () {
    final json = {
      'hoje': {
        'dia': '2026-09-07',
        'recebido_centavos': 84883,
        'chegam_qtd': 2,
        'no_patio_qtd': 4,
        'orcamentos_abertos_qtd': 1,
      },
      'mes': {
        'label': 'Setembro de 2026',
        'faturado_centavos': 104980,
        'recebido_centavos': 184873,
        'os_concluidas': 2,
        'ticket_medio_centavos': 52490,
        'mes_anterior': {'faturado_centavos': 0, 'recebido_centavos': 0},
      },
      'cobranca': {
        'pendentes': {'qtd': 1, 'total_centavos': 21990},
        'atrasados': {'qtd': 2, 'total_centavos': 69987},
      },
    };

    test('lê os três blocos', () {
      final r = Resumo.doJson(json);
      expect(r.hoje.recebidoCentavos, 84883);
      expect(r.hoje.noPatioQtd, 4);
      expect(r.mes.faturadoCentavos, 104980);
      expect(r.cobranca.atrasados.qtd, 2);
      expect(r.cobranca.atrasados.totalCentavos, 69987);
    });

    test('o rótulo do mês vem escrito do backend', () {
      // o app não monta nome de mês: "Setembro de 2026" é responsabilidade do servidor
      expect(Resumo.doJson(json).mes.label, 'Setembro de 2026');
    });
  });

  group('Extrato', () {
    final json = {
      'periodo': {'de': '2026-09-01', 'ate': '2026-09-07', 'label': '01/09/2026 a 07/09/2026'},
      'total_centavos': 84883,
      'estornos_centavos': 30000,
      'por_forma': [
        {'forma': 'pix', 'forma_label': 'Pix', 'total_centavos': 28230},
        {'forma': 'dinheiro', 'forma_label': 'Dinheiro', 'total_centavos': 16663},
      ],
      'lancamentos': [
        {
          'id': 1,
          'work_order_id': 9,
          'numero': 5,
          'cliente_nome': 'Ruan Oliveira',
          'valor_centavos': 18330,
          'forma': 'pix',
          'forma_label': 'Pix',
          'pago_em': '2026-09-07T22:50:00Z',
          'created_at': '2026-09-07T22:50:00Z',
          'observacao': null,
          'estornado_em': null,
          'estorno_motivo': null,
        },
        {
          'id': 2,
          'work_order_id': 9,
          'numero': 5,
          'cliente_nome': 'Ruan Oliveira',
          'valor_centavos': 30000,
          'forma': 'credito',
          'forma_label': 'Cartão de crédito',
          'pago_em': '2026-09-07T20:10:00Z',
          'created_at': '2026-09-07T20:10:00Z',
          'observacao': null,
          'estornado_em': '2026-09-07T21:00:00Z',
          'estorno_motivo': 'cartão negado depois',
        },
      ],
      'total': 2,
      'page': 1,
      'page_size': 50,
    };

    test('lê totais, formas e lançamentos', () {
      final e = Extrato.doJson(json);
      expect(e.periodoLabel, '01/09/2026 a 07/09/2026');
      expect(e.totalCentavos, 84883);
      expect(e.estornosCentavos, 30000);
      expect(e.porForma.first.formaLabel, 'Pix');
      expect(e.lancamentos.length, 2);
    });

    test('marca o estornado — a linha continua na lista, riscada', () {
      final e = Extrato.doJson(json);
      expect(e.lancamentos[0].estornado, isFalse);
      expect(e.lancamentos[1].estornado, isTrue);
      expect(e.lancamentos[1].estornoMotivo, 'cartão negado depois');
    });

    test('número da OS formatado, e "#id" quando ainda não tem número', () {
      final e = Extrato.doJson(json);
      expect(e.lancamentos.first.numeroFormatado, 'nº 005');

      // OS recebida ganha número; orçamento e agendamento ainda não têm, e caem no id
      final cru = Map<String, dynamic>.from((json['lancamentos'] as List).first as Map<String, dynamic>);
      cru['numero'] = null;
      expect(Lancamento.doJson(cru).numeroFormatado, '#9');
    });
  });

  group('OS: régua de cobrança', () {
    Map<String, dynamic> osJson({
      String? situacao,
      String? label,
      String? tone,
      String? vencimento,
      int desconto = 0,
    }) =>
        {
          'id': 9,
          'numero': 5,
          'status': 'concluido',
          'status_label': 'Concluído',
          'status_tone': 'ok',
          'cliente': {'nome': 'Ruan Oliveira', 'telefone': '5582999110001'},
          'veiculo': {'marca': 'Honda', 'modelo': 'Civic EX', 'placa': 'BRA2E19', 'cor': 'Prata'},
          'itens': const [],
          'acoes': const [],
          'desconto_centavos': desconto,
          'valor_total_centavos': 54990,
          'pago_centavos': 18330,
          'saldo_centavos': 36660,
          'aceita_pagamento': true,
          'situacao_cobranca': situacao,
          'situacao_cobranca_label': label,
          'situacao_cobranca_tone': tone,
          'vencimento': vencimento,
        };

    test('lê situação, rótulo e cor prontos do servidor', () {
      final os = OS.doJson(osJson(situacao: 'atrasado', label: 'Atrasado', tone: 'danger'));
      expect(os.situacaoCobranca, 'atrasado');
      expect(os.situacaoCobrancaLabel, 'Atrasado');
      expect(os.situacaoCobrancaTone, 'danger');
    });

    test('OS que não é cobrança vem com os três campos nulos', () {
      // orçamento, cancelada ou total zero: a tela não desenha etiqueta nenhuma
      final os = OS.doJson(osJson());
      expect(os.situacaoCobranca, isNull);
      expect(os.situacaoCobrancaLabel, isNull);
    });

    test('vencimento é convertido para a hora local', () {
      final os = OS.doJson(osJson(vencimento: '2026-09-25T23:59:00-03:00'));
      expect(os.vencimento, isNotNull);
      expect(os.vencimento!.isUtc, isFalse);
    });

    test('desconto entra no modelo, para a tela explicar a diferença do total', () {
      expect(OS.doJson(osJson(desconto: 5000)).descontoCentavos, 5000);
      expect(OS.doJson(osJson()).descontoCentavos, 0);
    });
  });

  group('Caixa e devedores', () {
    test('devedor traz a situação com rótulo e cor, e cai no status quando faltar', () {
      final comRegua = Devedor.doJson({
        'work_order_id': 9,
        'numero': 5,
        'cliente_nome': 'Ruan',
        'status': 'concluido',
        'status_label': 'Concluído',
        'status_tone': 'ok',
        'valor_total_centavos': 54990,
        'pago_centavos': 18330,
        'saldo_centavos': 36660,
        'situacao_cobranca': 'atrasado',
        'situacao_cobranca_label': 'Atrasado',
        'situacao_cobranca_tone': 'danger',
        'vencimento': null,
      });
      expect(comRegua.situacaoLabel, 'Atrasado');
      expect(comRegua.situacaoTone, 'danger');
      expect(comRegua.saldoCentavos, 36660);
    });
  });

  group('montarUrl', () {
    // O defeito que motivou estes testes só apareceu no aparelho: um `page_size: 100` (int) fazia
    // Uri.replace estourar ao MONTAR a requisição, e a tela dizia "sem conexão" com o wi-fi bom.
    test('converte número para texto — era isto que quebrava no aparelho', () {
      final u = montarUrl('http://x:8000', '/extrato', {'de': '2026-09-01', 'page_size': 100});
      expect(u.queryParameters['page_size'], '100');
      expect(u.queryParameters['de'], '2026-09-01');
    });

    test('omite valor nulo — filtro não escolhido não vira ?forma=null', () {
      final u = montarUrl('http://x:8000', '/extrato', {'de': '2026-09-01', 'forma': null});
      expect(u.queryParameters.containsKey('forma'), isFalse);
    });

    test('lista vira parâmetro repetido, que é como o backend lê', () {
      final u = montarUrl('http://x:8000', '/work-orders', {
        'status': ['recebido', 'em_execucao'],
      });
      expect(u.queryParametersAll['status'], ['recebido', 'em_execucao']);
    });

    test('sem query, a URL sai limpa (sem "?" pendurado)', () {
      expect(montarUrl('http://x:8000', '/patio').toString(), 'http://x:8000/api/v1/patio');
      expect(montarUrl('http://x:8000', '/patio', {}).toString(), 'http://x:8000/api/v1/patio');
      // mapa que só tinha nulos também não deixa "?" para trás
      expect(
        montarUrl('http://x:8000', '/patio', {'forma': null}).toString(),
        'http://x:8000/api/v1/patio',
      );
    });
  });

  group('mensagemDeErro', () {
    test('erro da API mostra a mensagem do servidor', () {
      expect(mensagemDeErro(ErroApi(409, 'Esta OS já está paga.')), 'Esta OS já está paga.');
    });

    test('falha que não é de rede NÃO diz "sem conexão"', () {
      // dizer "sem conexão" com sinal cheio é diagnóstico errado — e errado é pior que nenhum
      expect(mensagemDeErro(ArgumentError('bug nosso')), isNot(contains('Sem conexão')));
    });
  });

  group('data() e hora(): sempre no fuso da LOJA', () {
    test('formata dia e mês com dois dígitos', () {
      // 12:00 em Maceió, em qualquer aparelho: o dia é o mesmo
      expect(data(DateTime.utc(2026, 9, 5, 15)), '05/09');
      expect(data(DateTime.utc(2026, 12, 25, 15)), '25/12');
    });

    test('vencimento das 23:59 em Maceió NÃO vira o dia seguinte', () {
      // Este é o defeito que apareceu no emulador: 25/09 23:59 na loja é 26/09 02:59 em UTC, e o
      // app mostrava "vence 26/09" para um prazo marcado no dia 25.
      final venceDia25 = DateTime.utc(2026, 9, 26, 2, 59);
      expect(data(venceDia25), '25/09');
    });

    test('hora também é a da loja, não a do aparelho', () {
      expect(hora(DateTime.utc(2026, 9, 7, 22, 50)), '19:50');
      expect(hora(null), '');
    });

    test('não depende do fuso em que o aparelho está', () {
      // o mesmo instante, expresso com dois offsets diferentes, dá a mesma hora de loja
      final a = DateTime.parse('2026-09-07T22:50:00Z');
      final b = DateTime.parse('2026-09-07T19:50:00-03:00');
      final c = DateTime.parse('2026-09-08T07:50:00+09:00');
      expect(hora(a), hora(b));
      expect(hora(b), hora(c));
      expect(hora(a), '19:50');
    });
  });
}
