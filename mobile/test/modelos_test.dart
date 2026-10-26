import 'package:flutter_test/flutter_test.dart';
import 'package:kadosh_campo/modelos.dart';

/// O app não decide status nem cor: ele lê o payload. O que se testa aqui é a leitura — o pátio
/// desenha o card inteiro a partir dela, e um campo lido errado vira botão errado na mão do sócio.
void main() {
  Map<String, dynamic> payload({
    String status = 'em_execucao',
    List<Map<String, dynamic>> acoes = const [],
    Map<String, dynamic>? veiculo = const {'placa': 'BRA2E19', 'marca': 'Honda', 'modelo': 'Civic'},
    String? previsao,
    int total = 15000,
    int pago = 0,
  }) =>
      {
        'id': 7,
        'numero': 42,
        'status': status,
        'status_label': 'Em execução',
        'status_tone': 'gold',
        'cliente': {'nome': 'Rafael', 'telefone': '5582999990000'},
        'veiculo': veiculo,
        'itens': [
          {'id': 1, 'descricao': 'Polimento', 'valor_centavos': total},
        ],
        'acoes': acoes,
        'valor_total_centavos': total,
        'pago_centavos': pago,
        'saldo_centavos': total - pago,
        'previsao_conclusao': previsao,
      };

  Map<String, dynamic> acao(String status, {bool principal = false}) => {
        'status': status,
        'label': 'Pronto',
        'acao_label': 'Marcar pronto',
        'tone': 'ok',
        'requer_motivo': false,
        'principal': principal,
      };

  group('OS.doJson', () {
    test('junta marca e modelo, e aguenta veículo sem marca', () {
      expect(OS.doJson(payload()).veiculo, 'Honda Civic');
      final semMarca = OS.doJson(payload(veiculo: {'placa': 'ABC1234', 'modelo': 'Gol'}));
      expect(semMarca.veiculo, 'Gol');
    });

    test('aguenta OS sem veículo — orçamento nasce assim', () {
      final os = OS.doJson(payload(veiculo: null));
      expect(os.placa, isNull);
      expect(os.veiculo, '');
      expect(placaFormatada(os.placa), '—');
    });

    test('os campos só do detalhe têm padrão seguro na lista do pátio', () {
      final os = OS.doJson(payload());
      expect(os.aceitaPagamento, isFalse);
      expect(os.pagamentos, isEmpty);
      expect(os.observacoesEntrada, isNull);
    });
  });

  group('acaoPrincipal', () {
    test('devolve a que o backend marcou, não a primeira da lista', () {
      final os = OS.doJson(payload(
        acoes: [acao('recebido'), acao('aguardando_retirada', principal: true)],
      ));
      expect(os.acaoPrincipal?.status, 'aguardando_retirada');
    });

    test('sem passo esperado, o card fica sem botão em vez de chutar um', () {
      expect(OS.doJson(payload(acoes: [acao('recebido')])).acaoPrincipal, isNull);
      expect(OS.doJson(payload()).acaoPrincipal, isNull);
    });
  });

  group('atrasado', () {
    final passado = DateTime.now().toUtc().subtract(const Duration(hours: 2)).toIso8601String();
    final futuro = DateTime.now().toUtc().add(const Duration(hours: 2)).toIso8601String();

    test('passou da hora e ainda não ficou pronto', () {
      expect(OS.doJson(payload(previsao: passado)).atrasado, isTrue);
    });

    test('carro pronto não fica vermelho esperando o cliente aparecer', () {
      final os = OS.doJson(payload(status: 'aguardando_retirada', previsao: passado));
      expect(os.atrasado, isFalse);
    });

    test('sem previsão não existe atraso — OS sem serviço não nasce vermelha', () {
      expect(OS.doJson(payload()).atrasado, isFalse);
      expect(OS.doJson(payload(previsao: futuro)).atrasado, isFalse);
    });
  });

  group('placaFormatada', () {
    test('quebra a placa de 7 como o balcão lê', () {
      expect(placaFormatada('BRA2E19'), 'BRA-2E19');
    });

    test('deixa em paz o que não tem 7 caracteres', () {
      expect(placaFormatada('ABC12'), 'ABC12');
      expect(placaFormatada(''), '—');
      expect(placaFormatada(null), '—');
    });
  });

  group('numeroFormatado', () {
    test('usa o número da loja quando existe', () {
      expect(OS.doJson(payload()).numeroFormatado, 'nº 042');
    });

    test('orçamento ainda sem número cai no id', () {
      final j = payload()..['numero'] = null;
      expect(OS.doJson(j).numeroFormatado, '#7');
    });
  });
}
