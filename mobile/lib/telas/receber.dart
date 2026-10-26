import 'dart:math';

import 'package:flutter/material.dart';

import '../api.dart';
import '../modelos.dart';
import '../tema.dart';

/// Recepção do veículo em uma tela só.
///
/// A placa manda: é por ela que o balcão encontra quem já é cliente. Se achar, cliente e carro vêm
/// preenchidos; se não achar, cadastra na hora. O botão "Receber" é sempre seguro de repetir —
/// a chave de idempotência é gerada uma vez, ao abrir a tela.
class TelaReceber extends StatefulWidget {
  const TelaReceber({required this.api, super.key});
  final Api api;

  @override
  State<TelaReceber> createState() => _TelaReceberState();
}

class _TelaReceberState extends State<TelaReceber> {
  final _placa = TextEditingController();
  final _nome = TextEditingController();
  final _telefone = TextEditingController();
  final _modelo = TextEditingController();
  final _entrada = TextEditingController();
  final _foco = FocusNode();

  late final String _chave;
  List<Servico> _servicos = const [];
  final Set<int> _escolhidos = {};

  int? _clientId;
  int? _vehicleId;
  int? _agendadaId;
  String? _agendadaQuando;

  /// Cada busca leva um número. Resposta que chega fora de ordem é descartada: sem isto, a
  /// consulta antiga podia chegar por último e amarrar o carro errado à OS.
  int _busca = 0;

  bool _buscando = false;
  bool _enviando = false;

  /// Um envio já foi feito e não teve resposta: pode ter chegado. Corrigir um campo e tocar de
  /// novo faria o servidor repetir a recepção ANTIGA (mesma chave) e a correção sumiria em
  /// silêncio — então os campos travam até isso se resolver.
  bool _envioNoEscuro = false;

  String? _erro;
  String? _achado;
  String? _avisoBusca;

  @override
  void initState() {
    super.initState();
    // uma chave por abertura da tela: tocar duas vezes em Receber não abre duas OS
    _chave = 'app-${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(1 << 32)}';
    _carregarServicos();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _foco.requestFocus();
    });
  }

  @override
  void dispose() {
    _placa.dispose();
    _nome.dispose();
    _telefone.dispose();
    _modelo.dispose();
    _entrada.dispose();
    _foco.dispose();
    super.dispose();
  }

  Future<void> _carregarServicos() async {
    try {
      final j = await widget.api.get('/services', {'apenas_ativos': 'true', 'page_size': '200'});
      final itens = (j as Map<String, dynamic>)['items'] as List;
      if (mounted) {
        setState(() => _servicos =
            itens.map((e) => Servico.doJson(e as Map<String, dynamic>)).toList());
      }
    } catch (_) {
      // sem catálogo dá para receber assim mesmo: o serviço entra depois, pela tela da OS
    }
  }

  static String _so(String placa) => placa.toUpperCase().replaceAll(RegExp(r'[^A-Z0-9]'), '');

  /// Procura pela placa. Achou a placa EXATA: preenche tudo e trava. Qualquer outra coisa: o
  /// balcão digita o que falta.
  ///
  /// A busca do backend é difusa — casa modelo, marca e nome do cliente, e ordena pelo veículo
  /// mais recente. Pegar `veiculos.first` sem conferir recebia o carro errado, com o cliente
  /// errado junto, que é justamente o que esta tela tem de impedir.
  Future<void> _procurar() async {
    final digitado = _so(_placa.text);
    if (digitado.length < 3) {
      setState(() => _avisoBusca = 'Digite pelo menos 3 caracteres da placa.');
      return;
    }
    final meu = ++_busca;
    setState(() {
      _buscando = true;
      _erro = null;
      _avisoBusca = null;
    });
    try {
      final j = await widget.api.get('/search', {'q': digitado}) as Map<String, dynamic>;
      if (!mounted || meu != _busca) return;
      final veiculos = (j['veiculos'] as List?) ?? const [];
      Map<String, dynamic>? achado;
      for (final v in veiculos) {
        final item = v as Map<String, dynamic>;
        final placa = item['placa'] as String?;
        if (placa != null && _so(placa) == digitado) {
          achado = item;
          break;
        }
      }
      if (achado == null) {
        setState(() {
          _vehicleId = null;
          _clientId = null;
          _achado = null;
          _agendadaId = null;
          _avisoBusca = veiculos.isEmpty
              ? 'Placa não cadastrada. Preencha abaixo para cadastrar.'
              : 'Nenhum carro com essa placa exata. Preencha abaixo para cadastrar.';
        });
        return;
      }
      final cliente = achado['cliente'] as Map<String, dynamic>;
      final marca = achado['marca'] as String?;
      setState(() {
        _vehicleId = achado!['id'] as int;
        _clientId = cliente['id'] as int;
        _achado = '${cliente['nome']} · ${[?marca, achado['modelo']].join(' ')}';
      });
      await _procurarAgendamento(_vehicleId!, meu);
    } catch (_) {
      if (!mounted || meu != _busca) return;
      // Engolir a falha em silêncio era igual a "placa não cadastrada": o balcão cadastrava de
      // novo um cliente que já existe, e ninguém ficava sabendo.
      setState(() => _avisoBusca = 'Não deu para procurar. Confira a placa antes de cadastrar.');
    } finally {
      if (mounted && meu == _busca) setState(() => _buscando = false);
    }
  }

  /// Este carro tem hora marcada? Então a recepção é DAQUELA OS.
  ///
  /// Sem isto o app abria uma OS nova, a agendada ficava pendurada e depois contava como não
  /// comparecimento — com o carro no pátio e o faturamento partido em duas.
  Future<void> _procurarAgendamento(int vehicleId, int meu) async {
    try {
      final j = await widget.api.get('/work-orders', {
        'vehicle_id': '$vehicleId',
        'status': const ['agendado', 'confirmado'],
        'page_size': '5',
      }) as Map<String, dynamic>;
      if (!mounted || meu != _busca) return;
      final itens = (j['items'] as List?) ?? const [];
      if (itens.isEmpty) return;
      final os = itens.first as Map<String, dynamic>;
      final quando = os['scheduled_at'] as String?;
      setState(() {
        _agendadaId = os['id'] as int;
        _agendadaQuando = quando == null ? null : hora(DateTime.parse(quando).toLocal());
      });
    } catch (_) {
      // sem a consulta, recebe como OS nova — o dono conserta no painel
    }
  }

  void _soltarCarro() {
    setState(() {
      _vehicleId = null;
      _clientId = null;
      _achado = null;
      _agendadaId = null;
      _agendadaQuando = null;
      _avisoBusca = null;
    });
  }

  Future<void> _receber() async {
    setState(() {
      _enviando = true;
      _erro = null;
    });
    try {
      final corpo = <String, dynamic>{
        'idempotency_key': _chave,
        if (_agendadaId != null) 'work_order_id': _agendadaId,
        if (_agendadaId == null)
          'cliente': _clientId != null
              ? {'id': _clientId}
              : {
                  'nome': _nome.text.trim(),
                  if (_telefone.text.trim().isNotEmpty) 'telefone': _telefone.text.trim(),
                },
        if (_agendadaId == null)
          'veiculo': _vehicleId != null
              ? {'id': _vehicleId}
              : {
                  if (_placa.text.trim().isNotEmpty) 'placa': _placa.text.trim(),
                  'modelo': _modelo.text.trim(),
                },
        'itens': _escolhidos.map((id) => {'service_id': id}).toList(),
        if (_entrada.text.trim().isNotEmpty) 'observacoes_entrada': _entrada.text.trim(),
      };
      await widget.api.post('/work-orders/intake', corpo);
      if (mounted) Navigator.of(context).pop(true);
    } on ErroApi catch (e) {
      if (mounted) setState(() => _erro = e.mensagem);
    } catch (_) {
      if (mounted) {
        setState(() {
          _envioNoEscuro = true;
          _erro = 'Sem conexão. Toque em Receber de novo — não vai duplicar.';
        });
      }
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  bool get _podeReceber =>
      _agendadaId != null ||
      ((_clientId != null || _nome.text.trim().isNotEmpty) &&
          (_vehicleId != null || _modelo.text.trim().isNotEmpty));

  int get _totalEscolhido => _servicos
      .where((s) => _escolhidos.contains(s.id))
      .fold(0, (soma, s) => soma + s.valorBaseCentavos);

  @override
  Widget build(BuildContext context) {
    final jaCadastrado = _vehicleId != null;
    final travado = _envioNoEscuro;
    return PopScope(
      // sair no meio do envio deixava a OS aberta no servidor sem ninguém saber — e a próxima
      // tela de recepção viria com outra chave, criando a segunda OS do mesmo carro
      canPop: !_enviando,
      child: Scaffold(
        appBar: AppBar(title: const Text('Receber veículo')),
        body: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            TextField(
              controller: _placa,
              focusNode: _foco,
              enabled: !travado,
              textCapitalization: TextCapitalization.characters,
              autocorrect: false,
              textInputAction: TextInputAction.search,
              // Mexeu na placa, solta o carro que a busca tinha achado: senão o balcão digita a
              // placa nova, não procura, e recebe o veículo errado — com o cliente errado junto.
              onChanged: (_) => _soltarCarro(),
              onSubmitted: (_) => _procurar(),
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, letterSpacing: 1.5),
              decoration: InputDecoration(
                labelText: 'Placa',
                hintText: 'BRA2E19',
                suffixIcon: _buscando
                    ? const Padding(
                        padding: EdgeInsets.all(16),
                        child: SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2.4),
                        ),
                      )
                    : IconButton(
                        onPressed: travado ? null : _procurar,
                        icon: const Icon(Icons.search),
                        tooltip: 'Procurar',
                      ),
              ),
            ),
            if (_avisoBusca != null) ...[
              const SizedBox(height: 8),
              Text(
                _avisoBusca!,
                style: const TextStyle(fontSize: 14, color: Cores.alerta, height: 1.3),
              ),
            ],
            if (_achado != null) ...[
              const SizedBox(height: 10),
              _Caixa(
                cor: Cores.ok,
                icone: Icons.check_circle_outline,
                // a placa entra aqui de propósito: é o que prova que é o carro certo
                texto: '${placaFormatada(_placa.text.trim())} · $_achado',
                acao: travado ? null : TextButton(onPressed: _soltarCarro, child: const Text('Trocar')),
              ),
            ],
            if (_agendadaId != null) ...[
              const SizedBox(height: 10),
              _Caixa(
                cor: Cores.ouro,
                icone: Icons.event_available_outlined,
                texto: _agendadaQuando == null
                    ? 'Este carro tem agendamento. A recepção vai nele, sem abrir OS nova.'
                    : 'Agendado para ${_agendadaQuando!}. A recepção vai nesta OS, sem abrir OS nova.',
              ),
            ],
            if (!jaCadastrado) ...[
              const SizedBox(height: 14),
              TextField(
                controller: _modelo,
                enabled: !travado,
                onChanged: (_) => setState(() {}),
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Modelo', hintText: 'Civic EX'),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _nome,
                enabled: !travado,
                onChanged: (_) => setState(() {}),
                textCapitalization: TextCapitalization.words,
                decoration: const InputDecoration(labelText: 'Cliente'),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _telefone,
                enabled: !travado,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(
                  labelText: 'Telefone',
                  hintText: '(82) 99999-9999',
                  helperText: 'Sem ele não dá para avisar quando o carro ficar pronto',
                ),
              ),
            ],
            const SizedBox(height: 22),
            const _Rotulo('Como o carro chegou'),
            const SizedBox(height: 10),
            TextField(
              controller: _entrada,
              enabled: !travado,
              maxLines: 3,
              textCapitalization: TextCapitalization.sentences,
              decoration: const InputDecoration(
                hintText: 'Riscos, amassados, pertences, combustível…',
              ),
            ),
            const SizedBox(height: 6),
            const Text(
              'É o que defende a loja numa reclamação depois.',
              style: TextStyle(fontSize: 13, color: Cores.textoFraco),
            ),
            if (_servicos.isNotEmpty) ...[
              const SizedBox(height: 22),
              const _Rotulo('Serviços'),
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final s in _servicos)
                    FilterChip(
                      label: Text('${s.nome} · ${reais(s.valorBaseCentavos)}'),
                      selected: _escolhidos.contains(s.id),
                      onSelected: travado
                          ? null
                          : (marcado) => setState(
                                () => marcado ? _escolhidos.add(s.id) : _escolhidos.remove(s.id),
                              ),
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 10),
                      selectedColor: Cores.ouro.withValues(alpha: 0.18),
                      checkmarkColor: Cores.obsidiana,
                    ),
                ],
              ),
              const SizedBox(height: 8),
              if (_escolhidos.isEmpty)
                const Text(
                  'Pode lançar depois, pela tela da OS.',
                  style: TextStyle(fontSize: 13, color: Cores.textoFraco),
                )
              else
                Text(
                  'Total: ${reais(_totalEscolhido)}',
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
            ],
            if (_erro != null) ...[
              const SizedBox(height: 18),
              Text(_erro!, style: const TextStyle(color: Cores.perigo, fontSize: 14.5)),
            ],
            if (_envioNoEscuro) ...[
              const SizedBox(height: 8),
              const Text(
                'Os campos estão travados de propósito: se o envio anterior chegou, mudar algo '
                'aqui não valeria. Toque em Receber; se já entrou, o pátio mostra o carro.',
                style: TextStyle(fontSize: 13.5, color: Cores.alerta, height: 1.35),
              ),
            ],
            const SizedBox(height: 26),
            FilledButton(
              onPressed: _podeReceber && !_enviando ? _receber : null,
              child: _enviando
                  ? const SizedBox(
                      height: 22,
                      width: 22,
                      child: CircularProgressIndicator(strokeWidth: 2.4, color: Cores.marfim),
                    )
                  : Text(_agendadaId != null ? 'Receber agendamento' : 'Receber e abrir OS'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Rotulo extends StatelessWidget {
  const _Rotulo(this.texto);
  final String texto;

  @override
  Widget build(BuildContext context) => Text(
        texto.toUpperCase(),
        style: const TextStyle(
          fontSize: 12.5,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.4,
          color: Cores.textoFraco,
        ),
      );
}

class _Caixa extends StatelessWidget {
  const _Caixa({required this.cor, required this.icone, required this.texto, this.acao});
  final Color cor;
  final IconData icone;
  final String texto;
  final Widget? acao;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: cor.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: cor.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            Icon(icone, color: cor, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text(texto, style: const TextStyle(fontSize: 15, color: Cores.texto, height: 1.3)),
            ),
            ?acao,
          ],
        ),
      );
}
