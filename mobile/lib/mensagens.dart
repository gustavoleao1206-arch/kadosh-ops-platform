import 'modelos.dart';

/// Textos de WhatsApp, iguais aos do painel (`web/src/features/work-orders/mensagens.ts`).
///
/// O cliente recebe a mesma mensagem, venha ela do balcão ou do celular do sócio: primeiro nome,
/// carro com placa, e uma frase que não abre buraco quando a OS não tem veículo.
String veiculoTexto(OS os) {
  if (os.veiculo.isEmpty) return '';
  final placa = os.placa;
  return placa == null || placa.isEmpty ? os.veiculo : '${os.veiculo} (${placaFormatada(placa)})';
}

String textoPronto(OS os) {
  final carro = veiculoTexto(os);
  final oQue = carro.isEmpty ? 'Seu veículo está pronto' : 'Seu $carro está pronto';
  return 'Olá, ${primeiroNome(os.clienteNome)}! $oQue para retirada na Kadosh Detail. 🚗✨';
}
