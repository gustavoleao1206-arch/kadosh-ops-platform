import 'package:flutter_test/flutter_test.dart';
import 'package:kadosh_campo/dinheiro.dart';
import 'package:kadosh_campo/modelos.dart';

/// O campo de valor é o único lugar do app onde o dedo do sócio cria um número do zero. Errar aqui
/// é errar dinheiro, e o erro só aparece no fechamento do caixa — por isso ele tem teste.
void main() {
  TextEditingValue digitar(String texto, {TextEditingValue? antigo}) => MoedaFormatter()
      .formatEditUpdate(antigo ?? const TextEditingValue(), TextEditingValue(text: texto));

  group('reais', () {
    test('formata centavos com milhar', () {
      expect(reais(0), 'R\$ 0,00');
      expect(reais(5), 'R\$ 0,05');
      expect(reais(12990), 'R\$ 129,90');
      expect(reais(123450), 'R\$ 1.234,50');
      expect(reais(100000000), 'R\$ 1.000.000,00');
    });
  });

  group('centavosDe', () {
    test('lê de volta o que reais() escreveu', () {
      for (final c in [0, 5, 12990, 123450, 100000000]) {
        expect(centavosDe(reais(c)), c);
      }
    });

    test('ignora texto sem dígito', () {
      expect(centavosDe(''), 0);
      expect(centavosDe('R\$ ,'), 0);
    });

    test('texto colado gigante vira um número acima do teto, não um número plausível', () {
      // Cortar os 12 primeiros dígitos manteria as casas ALTAS e devolveria algo que parece
      // dinheiro de verdade. Melhor estourar o teto e ser recusado.
      expect(centavosDe('9' * 40), greaterThan(maximoCentavos));
    });
  });

  group('MoedaFormatter', () {
    test('empurra da direita para a esquerda, como maquininha', () {
      expect(digitar('5').text, 'R\$ 0,05');
      expect(digitar('50').text, 'R\$ 0,50');
      expect(digitar('5000').text, 'R\$ 50,00');
    });

    test('apagar tudo esvazia o campo em vez de deixar R\$ 0,00', () {
      expect(digitar('').text, '');
    });

    test('deixa o cursor no fim, senão o próximo dígito entra no meio do número', () {
      final v = digitar('12345');
      expect(v.selection.baseOffset, v.text.length);
    });

    test('trava no teto do backend em vez de mandar um 422 para a tela', () {
      const antigo = TextEditingValue(text: 'R\$ 1.000.000,00');
      expect(digitar('1000000000', antigo: antigo).text, 'R\$ 1.000.000,00');
    });
  });
}
