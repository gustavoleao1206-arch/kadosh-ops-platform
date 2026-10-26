import 'dart:math';

import 'package:flutter/material.dart';

import '../api.dart';
import '../dinheiro.dart';
import '../modelos.dart';
import '../tema.dart';
import '../ui.dart';

/// A OS aberta: o que tem no carro, quanto é, quanto falta e o próximo passo.
///
/// É a tela da entrega. O sócio chega aqui pelo card do pátio, lança o serviço combinado no pátio,
/// recebe o dinheiro e conclui — nessa ordem, sem sair da tela. O que continua sendo do painel é
/// desconto, cadastro e edição de valor de serviço.
class TelaOS extends StatefulWidget {
  const TelaOS({required this.api, required this.osId, super.key});
  final Api api;
  final int osId;

  @override
  State<TelaOS> createState() => _TelaOSState();
}

class _TelaOSState extends State<TelaOS> {
  OS? _os;
  List<FormaPagamento> _formas = const [];
  List<Servico> _catalogo = const [];
  final Set<int> _aLancar = {};

  String? _forma;
  final _valor = TextEditingController();
  final _motivo = TextEditingController();
  late String _chavePagamento;
  String _chaveItem = '';

  bool _carregando = true;
  bool _ocupado = false;
  String? _erro;

  /// O dedo já mexeu no campo de valor. A partir daí o servidor não o sobrescreve — mesma regra
  /// do painel. Sem ela, digitar um sinal de R$ 50 e depois puxar a lista repunha o total no
  /// campo, e o toque seguinte cobrava o total inteiro.
  bool _valorTocado = false;

  /// Um envio de pagamento falhou sem resposta: pode ter chegado. Enquanto isso não se resolve, o
  /// valor fica travado — mudá-lo e tocar de novo faria o servidor repetir o lançamento ANTIGO
  /// (mesma chave) e o app anunciaria um número que não entrou no caixa.
  bool _pagamentoNoEscuro = false;

  /// O pátio só se dá ao trabalho de recarregar se alguma coisa mudou aqui dentro.
  bool _mudou = false;

  @override
  void initState() {
    super.initState();
    _chavePagamento = _novaChave('pg');
    _buscar();
    _carregarApoio();
  }

  @override
  void dispose() {
    _valor.dispose();
    _motivo.dispose();
    super.dispose();
  }

  String _novaChave(String prefixo) =>
      '$prefixo-${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(1 << 32)}';

  void _aplicar(dynamic corpo) {
    if (corpo is! Map<String, dynamic>) return;
    final os = OS.doJson(corpo);
    setState(() {
      _os = os;
      _erro = null;
      _carregando = false;
      if (!_valorTocado) {
        _valor.text = os.saldoCentavos > 0 ? reais(os.saldoCentavos) : '';
      }
    });
  }

  Future<void> _buscar() async {
    try {
      final j = await widget.api.get('/work-orders/${widget.osId}');
      if (!mounted) return;
      _aplicar(j);
      // uma requisição secundária não pode esconder o bloco de receber dinheiro: se ela falhou na
      // abertura, o refresh é a segunda chance
      if (_formas.isEmpty || _catalogo.isEmpty) await _carregarApoio();
    } on ErroApi catch (e) {
      if (mounted) {
        setState(() {
          _erro = e.mensagem;
          _carregando = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _erro = 'Sem conexão. Puxe para tentar de novo.';
          _carregando = false;
        });
      }
    }
  }

  Future<void> _carregarApoio() async {
    try {
      final formas = await widget.api.get('/payment-methods') as List;
      final servicos = await widget.api.get('/services', {'apenas_ativos': 'true', 'page_size': '200'});
      if (!mounted) return;
      setState(() {
        _formas = formas.map((e) => FormaPagamento.doJson(e as Map<String, dynamic>)).toList();
        _forma ??= _formas.isEmpty ? null : _formas.first.valor;
        _catalogo = ((servicos as Map<String, dynamic>)['items'] as List)
            .map((e) => Servico.doJson(e as Map<String, dynamic>))
            .toList();
      });
    } catch (_) {
      // o `_buscar` seguinte tenta de novo; a tela avisa que ficou sem
    }
  }

  // ---------------------------------------------------------------- status

  Future<void> _mudarStatus(Acao acao) async {
    final os = _os;
    if (os == null || _ocupado) return;

    if (acao.status == 'concluido' && os.aceitaPagamento && os.saldoCentavos > 0) {
      final seguir = await _confirmar(
        'Entregar devendo?',
        'Ainda faltam ${reais(os.saldoCentavos)}. Depois de concluir, só o dono reabre esta OS.',
        'Entregar assim mesmo',
      );
      if (seguir != true) return;
    }
    if (acao.status == 'cancelado' && os.pagoCentavos > 0) {
      final seguir = await _confirmar(
        'Cancelar com dinheiro recebido?',
        'Esta OS já recebeu ${reais(os.pagoCentavos)}. O cancelamento não devolve nada — '
            'o estorno é lançamento à parte.',
        'Cancelar mesmo assim',
      );
      if (seguir != true) return;
    }

    String? motivo;
    if (acao.requerMotivo) {
      motivo = await _pedirMotivo(acao.acaoLabel);
      if (motivo == null) return;
    }

    setState(() => _ocupado = true);
    try {
      final resposta = await widget.api.post('/work-orders/${os.id}/transition', {
        'to_status': acao.status,
        'expected_status': os.status,
        'motivo': ?motivo,
      });
      _mudou = true;
      if (!mounted) return;
      _aplicar(resposta); // a própria resposta já traz a OS inteira: um round-trip a menos
      _aviso(acao.label);
    } on ErroApi catch (e) {
      // Pode ser que o toque anterior tenha chegado. Recarrega e olha antes de gritar erro.
      if (e.talvezJaFeito) {
        await _buscar();
        if (!mounted) return;
        if (_os?.status == acao.status) {
          _mudou = true;
          _aviso(acao.label);
          return;
        }
      }
      if (mounted) _aviso(e.mensagem, erro: true);
    } catch (_) {
      if (mounted) _aviso('Sem conexão. A OS não mudou de status.', erro: true);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<String?> _pedirMotivo(String titulo) async {
    _motivo.clear();
    final confirmou = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(titulo),
        // O controller mora no State da tela, não aqui: descartá-lo logo depois do `await` o
        // matava enquanto o diálogo ainda estava saindo de cena, com o campo montado.
        content: TextField(
          controller: _motivo,
          autofocus: true,
          maxLines: 2,
          decoration: const InputDecoration(labelText: 'Motivo'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Voltar')),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: FilledButton.styleFrom(minimumSize: const Size(96, 48)),
            child: const Text('Confirmar'),
          ),
        ],
      ),
    );
    if (confirmou != true) return null;
    final texto = _motivo.text.trim();
    if (texto.isEmpty) {
      // antes o diálogo fechava e nada acontecia, sem uma palavra
      _aviso('Escreva o motivo — ele fica no histórico da OS.', erro: true);
      return null;
    }
    return texto;
  }

  // ---------------------------------------------------------------- serviços

  void _marcar(int id, bool marcado) {
    setState(() {
      if (marcado) {
        // uma chave por lançamento pretendido, cunhada na primeira escolha e trocada só no
        // sucesso: gerá-la no toque do botão deixaria a idempotência do item inerte
        if (_aLancar.isEmpty) _chaveItem = _novaChave('it');
        _aLancar.add(id);
      } else {
        _aLancar.remove(id);
      }
    });
  }

  Future<void> _lancarServicos() async {
    final os = _os;
    if (os == null || _aLancar.isEmpty || _chaveItem.isEmpty || _ocupado) return;
    setState(() => _ocupado = true);
    try {
      final corpo = _aLancar
          .map((id) => {'service_id': id, 'idempotency_key': '$_chaveItem-$id'})
          .toList();
      final resposta = await widget.api.post('/work-orders/${os.id}/items', corpo);
      _mudou = true;
      if (!mounted) return;
      setState(() {
        _aLancar.clear();
        _chaveItem = '';
        // o total mudou: o valor a receber volta a mandar no campo
        _valorTocado = false;
      });
      _aplicar(resposta);
      _aviso('Serviço lançado.');
    } on ErroApi catch (e) {
      if (mounted) _aviso(e.mensagem, erro: true);
    } catch (_) {
      if (mounted) _aviso('Sem conexão. Toque em Lançar de novo — não vai duplicar.', erro: true);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  // ---------------------------------------------------------------- dinheiro

  Future<void> _pagar() async {
    final os = _os;
    final forma = _forma;
    final centavos = centavosDe(_valor.text);
    if (os == null || forma == null || centavos <= 0 || _ocupado) return;

    final antes = os.pagoCentavos;
    setState(() => _ocupado = true);
    try {
      final resposta = await widget.api.post('/work-orders/${os.id}/payments', {
        'valor_centavos': centavos,
        'forma': forma,
        'idempotency_key': _chavePagamento,
      });
      // chave nova só depois de dar certo: enquanto não deu, repetir o toque tem que cair na mesma
      _chavePagamento = _novaChave('pg');
      _mudou = true;
      if (!mounted) return;
      setState(() {
        _valorTocado = false;
        _pagamentoNoEscuro = false;
      });
      _aplicar(resposta);
      FocusScope.of(context).unfocus();
      // O que o servidor gravou, não o que estava no campo: num retry a API devolve o lançamento
      // original, e anunciar o número local diria "R$ 80 lançado" com R$ 50 no caixa.
      final entrou = (_os?.pagoCentavos ?? antes) - antes;
      _aviso(entrou > 0 ? 'Recebido ${reais(entrou)}.' : 'Este pagamento já estava lançado.');
    } on ErroApi catch (e) {
      if (mounted) _aviso(e.mensagem, erro: true);
    } catch (_) {
      if (mounted) {
        setState(() => _pagamentoNoEscuro = true);
        _aviso('Sem conexão. Toque em Lançar de novo — não vai duplicar.', erro: true);
      }
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  Future<void> _estornar(Pagamento p) async {
    final os = _os;
    if (os == null || _ocupado) return;
    final motivo = await _pedirMotivo('Estornar ${reais(p.valorCentavos)}');
    if (motivo == null) return;

    setState(() => _ocupado = true);
    try {
      final resposta = await widget.api.post(
        '/work-orders/${os.id}/payments/${p.id}/estorno',
        {'motivo': motivo},
      );
      _mudou = true;
      if (!mounted) return;
      setState(() => _valorTocado = false);
      _aplicar(resposta);
      _aviso('Lançamento estornado.');
    } on ErroApi catch (e) {
      if (mounted) _aviso(e.mensagem, erro: true);
    } catch (_) {
      if (mounted) _aviso('Sem conexão. O estorno não foi lançado.', erro: true);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  // ---------------------------------------------------------------- avisos

  Future<bool?> _confirmar(String titulo, String texto, String confirmar) => showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(titulo),
          content: Text(texto, style: const TextStyle(fontSize: 15, height: 1.35)),
          actions: [
            TextButton(onPressed: () => Navigator.of(ctx).pop(false), child: const Text('Voltar')),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              style: FilledButton.styleFrom(minimumSize: const Size(96, 48)),
              child: Text(confirmar),
            ),
          ],
        ),
      );

  void _aviso(String texto, {bool erro = false}) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(
        SnackBar(
          content: Text(texto, style: const TextStyle(fontSize: 15)),
          backgroundColor: erro ? Cores.perigo : Cores.ok,
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final os = _os;
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (jaSaiu, _) {
        if (jaSaiu) return;
        Navigator.of(context).pop(_mudou);
      },
      child: Scaffold(
        appBar: AppBar(title: Text(os == null ? 'OS' : 'OS ${os.numeroFormatado}')),
        body: _carregando
            ? const Center(child: CircularProgressIndicator())
            : RefreshIndicator(
                onRefresh: _buscar,
                child: ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
                  children: [
                    // O erro vem no topo, como no pátio. No rodapé de uma OS com serviços,
                    // lançamentos e botões ele ficava abaixo da dobra e ninguém via.
                    if (_erro != null) _Faixa(texto: _erro!),
                    if (os == null)
                      const Text(
                        'OS não encontrada.',
                        style: TextStyle(color: Cores.perigo, fontSize: 15),
                      )
                    else
                      ..._corpo(os),
                  ],
                ),
              ),
      ),
    );
  }

  List<Widget> _corpo(OS os) {
    final principal = os.acaoPrincipal;
    final outras = os.acoes.where((a) => !a.principal).toList();
    final podeLancar = !['cancelado', 'concluido'].contains(os.status);
    return [
      Row(
        children: [
          Expanded(
            child: Text(
              placaFormatada(os.placa),
              style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w700, letterSpacing: 0.5),
            ),
          ),
          Etiqueta(os.statusLabel, tone: os.statusTone),
        ],
      ),
      const SizedBox(height: 3),
      Text('${os.veiculo} · ${os.clienteNome}', style: const TextStyle(fontSize: 16)),
      if (os.observacoesEntrada != null && os.observacoesEntrada!.isNotEmpty) ...[
        const SizedBox(height: 14),
        _Bloco(
          titulo: 'Como chegou',
          filhos: [
            Text(os.observacoesEntrada!, style: const TextStyle(fontSize: 14.5, height: 1.35)),
          ],
        ),
      ],
      const SizedBox(height: 18),
      _Bloco(
        titulo: 'Serviços',
        filhos: [
          if (os.itens.isEmpty)
            const Text(
              'Nenhum serviço lançado ainda.',
              style: TextStyle(fontSize: 14.5, color: Cores.textoFraco),
            ),
          for (final i in os.itens)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                children: [
                  Expanded(child: Text(i.descricao, style: const TextStyle(fontSize: 15))),
                  Text(reais(i.valorCentavos), style: const TextStyle(fontSize: 15)),
                ],
              ),
            ),
          const Divider(height: 22, color: Cores.linha),
          // O desconto explica a diferença entre a soma dos serviços e o total. Sem esta linha, o
          // sócio soma os itens na cabeça, não bate, e desconfia do sistema — ou do dono.
          if (os.descontoCentavos > 0)
            _Linha('Desconto', '− ${reais(os.descontoCentavos)}', cor: Cores.textoFraco),
          _Linha('Total', reais(os.valorTotalCentavos), forte: true),
          if (os.pagoCentavos > 0) _Linha('Recebido', reais(os.pagoCentavos), cor: Cores.ok),
          // sobre dinheiro, quem manda é `aceita_pagamento` — não o sinal do saldo. Sem isso a
          // tela escrevia "falta R$ X" numa OS cancelada.
          if (os.aceitaPagamento && os.saldoCentavos > 0)
            _Linha(
              'Falta',
              reais(os.saldoCentavos),
              // a cor da régua, não uma escolha do app: atrasado é vermelho, a receber é âmbar
              cor: Cores.doTone(os.situacaoCobrancaTone ?? 'warn'),
              forte: true,
            ),
          if (os.aceitaPagamento && os.saldoCentavos == 0 && os.valorTotalCentavos > 0)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text('Quitado.', style: TextStyle(fontSize: 15, color: Cores.ok)),
            ),
          // Situação e prazo, com o rótulo que o servidor mandou. Definir a data é do painel: no
          // celular, ao lado dos botões de status, um toque errado mudaria a régua de cobrança.
          if (os.situacaoCobrancaLabel != null) ...[
            const SizedBox(height: 10),
            Row(
              children: [
                EtiquetaCobranca(os),
                if (os.vencimento != null) ...[
                  const SizedBox(width: 8),
                  Text(
                    'vence ${data(os.vencimento!)}',
                    style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                  ),
                ] else if (os.situacaoCobranca == 'atrasado') ...[
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'entregue sem prazo combinado',
                      style: TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                    ),
                  ),
                ],
              ],
            ),
          ],
        ],
      ),
      // O serviço é combinado no pátio, com o carro já dentro — a recepção até promete isso em
      // texto. Sem este bloco o sócio ficava esperando o dono abrir o painel, e nem pagamento
      // conseguia lançar (o backend recusa receber numa OS sem serviço).
      if (podeLancar) ...[
        const SizedBox(height: 14),
        _Bloco(
          titulo: 'Lançar serviço',
          filhos: [
            if (_catalogo.isEmpty)
              const Text(
                'Catálogo não carregou. Puxe a tela para baixo para tentar de novo.',
                style: TextStyle(fontSize: 14.5, color: Cores.alerta),
              )
            else ...[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final s in _catalogo)
                    FilterChip(
                      label: Text('${s.nome} · ${reais(s.valorBaseCentavos)}'),
                      selected: _aLancar.contains(s.id),
                      onSelected: _ocupado ? null : (m) => _marcar(s.id, m),
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 10),
                      selectedColor: Cores.ouro.withValues(alpha: 0.18),
                      checkmarkColor: Cores.obsidiana,
                    ),
                ],
              ),
              if (_aLancar.isNotEmpty) ...[
                const SizedBox(height: 14),
                FilledButton(
                  onPressed: _ocupado ? null : _lancarServicos,
                  child: Text('Lançar ${_aLancar.length == 1 ? 'serviço' : '${_aLancar.length} serviços'}'),
                ),
              ],
              const SizedBox(height: 6),
              const Text(
                'Preço combinado diferente do catálogo é ajuste do painel.',
                style: TextStyle(fontSize: 13, color: Cores.textoFraco),
              ),
            ],
          ],
        ),
      ],
      if (os.pagamentos.isNotEmpty) ...[
        const SizedBox(height: 14),
        _Bloco(
          titulo: 'Lançamentos',
          filhos: [
            for (final p in os.pagamentos)
              Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        '${p.formaLabel} · ${hora(p.pagoEm)}${p.estornado ? ' · estornado' : ''}',
                        style: TextStyle(
                          fontSize: 14.5,
                          color: p.estornado ? Cores.textoFraco : Cores.texto,
                        ),
                      ),
                    ),
                    Text(
                      reais(p.valorCentavos),
                      style: TextStyle(
                        fontSize: 14.5,
                        color: p.estornado ? Cores.textoFraco : Cores.texto,
                        decoration: p.estornado ? TextDecoration.lineThrough : null,
                      ),
                    ),
                    // quem pode estornar é decisão do backend, que já vem calculada no payload
                    if (p.podeEstornar)
                      IconButton(
                        onPressed: _ocupado ? null : () => _estornar(p),
                        icon: const Icon(Icons.undo, size: 20),
                        tooltip: 'Estornar',
                        visualDensity: VisualDensity.compact,
                      ),
                  ],
                ),
              ),
          ],
        ),
      ],
      if (os.aceitaPagamento) ...[
        const SizedBox(height: 14),
        _Bloco(
          titulo: 'Receber pagamento',
          filhos: [
            if (_formas.isEmpty)
              const Text(
                'As formas de pagamento não carregaram. Puxe a tela para baixo para tentar de novo.',
                style: TextStyle(fontSize: 14.5, color: Cores.alerta),
              )
            else ...[
              if (_pagamentoNoEscuro)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    'O último envio não teve resposta. Toque em Lançar de novo com o mesmo valor — '
                    'se ele já entrou, nada é cobrado duas vezes. Para mudar o valor, confira '
                    'antes em Lançamentos.',
                    style: TextStyle(fontSize: 13.5, color: Cores.alerta, height: 1.35),
                  ),
                ),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final f in _formas)
                    ChoiceChip(
                      label: Text(f.label),
                      selected: _forma == f.valor,
                      onSelected: _pagamentoNoEscuro ? null : (_) => setState(() => _forma = f.valor),
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 10),
                      selectedColor: Cores.ouro.withValues(alpha: 0.18),
                    ),
                ],
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _valor,
                enabled: !_pagamentoNoEscuro,
                keyboardType: const TextInputType.numberWithOptions(decimal: false),
                inputFormatters: [MoedaFormatter()],
                onChanged: (_) => setState(() => _valorTocado = true),
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
                decoration: InputDecoration(
                  labelText: 'Valor',
                  suffixIcon: _valor.text.isEmpty
                      ? null
                      : IconButton(
                          onPressed: () => setState(() {
                            _valor.clear();
                            _valorTocado = true;
                          }),
                          icon: const Icon(Icons.close),
                          tooltip: 'Limpar',
                        ),
                ),
              ),
              const SizedBox(height: 14),
              FilledButton(
                onPressed: centavosDe(_valor.text) > 0 && !_ocupado ? _pagar : null,
                child: _ocupado
                    ? const SizedBox(
                        height: 22,
                        width: 22,
                        child: CircularProgressIndicator(strokeWidth: 2.4, color: Cores.marfim),
                      )
                    : const Text('Lançar pagamento'),
              ),
              // o teclado cobre o rodapé: sem esta folga o botão fica atrás dele
              const SizedBox(height: 4),
            ],
          ],
        ),
      ],
      if (principal != null) ...[
        const SizedBox(height: 22),
        FilledButton(
          onPressed: _ocupado ? null : () => _mudarStatus(principal),
          child: Text(principal.acaoLabel),
        ),
      ],
      for (final a in outras) ...[
        const SizedBox(height: 10),
        OutlinedButton(
          onPressed: _ocupado ? null : () => _mudarStatus(a),
          style: a.tone == 'danger'
              ? OutlinedButton.styleFrom(
                  foregroundColor: Cores.perigo,
                  side: BorderSide(color: Cores.perigo.withValues(alpha: 0.4)),
                )
              : null,
          child: Text(a.acaoLabel),
        ),
      ],
    ];
  }
}

class _Faixa extends StatelessWidget {
  const _Faixa({required this.texto});
  final String texto;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 14),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Cores.perigo.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Cores.perigo.withValues(alpha: 0.3)),
        ),
        child: Text(texto, style: const TextStyle(color: Cores.perigo, fontSize: 14.5)),
      );
}

class _Bloco extends StatelessWidget {
  const _Bloco({required this.titulo, required this.filhos});
  final String titulo;
  final List<Widget> filhos;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                titulo.toUpperCase(),
                style: const TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.4,
                  color: Cores.textoFraco,
                ),
              ),
              const SizedBox(height: 12),
              ...filhos,
            ],
          ),
        ),
      );
}

class _Linha extends StatelessWidget {
  const _Linha(this.rotulo, this.valor, {this.cor, this.forte = false});
  final String rotulo;
  final String valor;
  final Color? cor;
  final bool forte;

  @override
  Widget build(BuildContext context) {
    final estilo = TextStyle(
      fontSize: forte ? 17 : 15,
      fontWeight: forte ? FontWeight.w700 : FontWeight.w500,
      color: cor ?? Cores.texto,
    );
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          Expanded(child: Text(rotulo, style: estilo)),
          Text(valor, style: estilo),
        ],
      ),
    );
  }
}
