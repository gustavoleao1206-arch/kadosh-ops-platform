import 'package:flutter/services.dart';

import 'modelos.dart';

/// Teto do backend (`valor_centavos le=100_000_000`). Deixar o campo aceitar mais só adiaria o
/// erro para o 422 depois do toque.
const maximoCentavos = 100000000; // R$ 1.000.000,00

/// "R$ 1.234,50" -> 123450. Só os dígitos importam; o resto é enfeite do formatador.
int centavosDe(String texto) {
  final digitos = texto.replaceAll(RegExp(r'\D'), '');
  if (digitos.isEmpty) return 0;
  // Mais de 12 dígitos já passou de qualquer teto: devolve algo acima do limite em vez de cortar.
  // Cortar pela esquerda mantinha as casas altas e transformaria um texto colado gigante num
  // número plausível — hoje o teto recusa, mas seria corrupção silenciosa no dia em que ele subir.
  if (digitos.length > 12) return maximoCentavos + 1;
  return int.parse(digitos);
}

/// Digitação em centavos, da direita para a esquerda — como toda maquininha.
///
/// Sem isto, "50" é ambíguo: cinquenta reais ou cinquenta centavos? Aqui não é: cada tecla empurra
/// uma casa, e o campo mostra o valor já formatado enquanto o dedo anda.
class MoedaFormatter extends TextInputFormatter {
  @override
  TextEditingValue formatEditUpdate(TextEditingValue antigo, TextEditingValue novo) {
    final centavos = centavosDe(novo.text);
    if (centavos == 0) return const TextEditingValue();
    if (centavos > maximoCentavos) return antigo;
    final texto = reais(centavos);
    return TextEditingValue(
      text: texto,
      selection: TextSelection.collapsed(offset: texto.length),
    );
  }
}
