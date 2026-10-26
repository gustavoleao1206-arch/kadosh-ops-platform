/// A mensagem de WhatsApp que sai do celular do sócio.
///
/// O painel tem a gêmea em `web/src/features/work-orders/mensagens.test.ts`, e as expectativas
/// literais dos dois lados são as mesmas de propósito: o cliente recebe o MESMO texto, venha ele
/// do balcão ou do pátio. Se um dos dois for alterado sozinho, um destes dois arquivos falha — que
/// é a única forma de perceber a divergência antes do cliente.
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:kadosh_campo/mensagens.dart';
import 'package:kadosh_campo/modelos.dart';

OS os({String nome = 'Ruan Oliveira da Silva', String? marca = 'Honda', String modelo = 'Civic EX', String? placa = 'BRA2E19'}) {
  final veiculo = <String, dynamic>{'marca': marca, 'modelo': modelo, 'placa': placa, 'cor': 'Prata'};
  return OS.doJson({
    'id': 9,
    'numero': 5,
    'status': 'aguardando_retirada',
    'status_label': 'Aguardando retirada',
    'status_tone': 'ok',
    'cliente': {'nome': nome, 'telefone': '5582999110001'},
    'veiculo': modelo.isEmpty ? null : veiculo,
    'itens': const [],
    'acoes': const [],
    'valor_total_centavos': 12990,
    'pago_centavos': 0,
    'saldo_centavos': 12990,
  });
}

void main() {
  group('textoPronto', () {
    test('chama o cliente pelo primeiro nome', () {
      // "Olá, Ruan Oliveira da Silva!" soa a cobrança de banco, não à estética que ele conhece
      final texto = textoPronto(os());
      expect(texto, contains('Olá, Ruan!'));
      expect(texto, isNot(contains('Oliveira')));
    });

    test('nomeia o carro com marca, modelo e placa formatada', () {
      expect(textoPronto(os()), contains('Honda Civic EX (BRA-2E19)'));
    });

    test('sem veículo, a frase não abre buraco', () {
      final texto = textoPronto(os(modelo: ''));
      expect(texto, contains('Seu veículo está pronto'));
      expect(texto, isNot(contains('  ')));
    });

    test('veículo sem placa não vira parêntese vazio', () {
      final texto = textoPronto(os(placa: null));
      expect(texto, contains('Honda Civic EX'));
      expect(texto, isNot(contains('()')));
    });

    test('veículo sem marca não começa com espaço', () {
      final texto = textoPronto(os(marca: null, modelo: 'Gol', placa: 'ABC1D23'));
      expect(texto, contains('Gol (ABC-1D23)'));
      expect(texto, isNot(contains('  Gol')));
    });

    test('fecha com o nome comercial e sem vocabulário interno', () {
      final texto = textoPronto(os());
      expect(texto, contains('Kadosh Detail'));
      // decisão de marca: nada de "ritual" ou "sagrado" em material que chega ao cliente
      expect(texto.toLowerCase(), isNot(matches(RegExp(r'ritual|sagrad'))));
    });
  });

  group('paridade com o painel', () {
    test('a frase é literalmente a mesma que o painel monta', () {
      // Copiada de mensagens.ts. Se o painel mudar o texto, esta linha falha — e a divergência
      // aparece aqui, não na conversa do cliente.
      expect(
        textoPronto(os()),
        'Olá, Ruan! Seu Honda Civic EX (BRA-2E19) está pronto para retirada na Kadosh Detail. 🚗✨',
      );
    });

    test('e a versão sem veículo também', () {
      expect(
        textoPronto(os(modelo: '')),
        'Olá, Ruan! Seu veículo está pronto para retirada na Kadosh Detail. 🚗✨',
      );
    });
  });
}
