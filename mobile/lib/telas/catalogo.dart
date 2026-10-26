import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../modelos.dart';
import '../tema.dart';
import '../ui.dart';

/// A tabela de preços, do jeito que ela é usada no balcão: alguém pergunta quanto custa, e a
/// resposta precisa sair em dois toques.
///
/// SÓ LEITURA, e não por escolha de desenho: o servidor exige administrador para criar e editar
/// serviço (`POST/PATCH/DELETE /services` pedem AdminUser). Botão de editar aqui daria 403 na cara
/// do sócio — pior que não ter botão. Preço é decisão do dono, e muda no painel.
///
/// Serviço desativado fica escondido por padrão: quem consulta preço quer o que está à venda hoje.
/// O botão "mostrar desativados" existe porque OS antiga pode citar um serviço que saiu de linha, e
/// aí a pergunta muda de "quanto custa" para "o que era isso".
class TelaCatalogo extends StatefulWidget {
  const TelaCatalogo({required this.api, super.key});

  final Api api;

  @override
  State<TelaCatalogo> createState() => _TelaCatalogoState();
}

class _TelaCatalogoState extends State<TelaCatalogo> {
  final _busca = TextEditingController();
  Timer? _debounce;

  List<Servico> _itens = const [];
  bool _mostrarInativos = false;
  bool _carregando = true;
  String? _erro;

  /// Mesma trava da tela de clientes: resposta atrasada de uma busca antiga não pinta a tela.
  int _geracao = 0;

  /// O aberto é UM só: catálogo de estética tem dezenas de linhas, e várias descrições abertas ao
  /// mesmo tempo transformam a tabela de preços num texto corrido.
  int? _aberto;

  @override
  void initState() {
    super.initState();
    _buscar();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _busca.dispose();
    super.dispose();
  }

  void _aoDigitar(String _) {
    setState(() {});
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 350), _buscar);
  }

  Future<void> _buscar() async {
    final minha = ++_geracao;
    setState(() {
      _carregando = true;
      _erro = null;
    });
    final termo = _busca.text.trim();
    try {
      final j = await widget.api.get('/services', {
        if (termo.isNotEmpty) 'q': termo,
        'apenas_ativos': !_mostrarInativos,
        'page_size': 200,
      }) as Map<String, dynamic>;
      if (!mounted || minha != _geracao) return;
      setState(() {
        _itens = ((j['items'] as List?) ?? const [])
            .map((s) => Servico.doJson(s as Map<String, dynamic>))
            .toList();
        _carregando = false;
      });
    } catch (e) {
      if (!mounted || minha != _geracao) return;
      setState(() {
        _erro = mensagemDeErro(e);
        _carregando = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final termo = _busca.text.trim();

    return Scaffold(
      appBar: AppBar(title: const Text('Catálogo')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: TextField(
              controller: _busca,
              onChanged: _aoDigitar,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _buscar(),
              decoration: InputDecoration(
                hintText: 'Buscar serviço',
                prefixIcon: const Icon(Icons.search, size: 20),
                suffixIcon: _busca.text.isEmpty
                    ? null
                    : IconButton(
                        icon: const Icon(Icons.close, size: 20),
                        tooltip: 'Limpar',
                        onPressed: () {
                          _busca.clear();
                          _buscar();
                        },
                      ),
              ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _buscar,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(16, 6, 16, 32),
                children: [
                  if (_erro != null) ...[
                    Faixa(_erro!, aoTocar: _buscar, icone: Icons.wifi_off),
                    const SizedBox(height: 14),
                  ],
                  if (_carregando && _itens.isEmpty)
                    const Column(
                      children: [
                        Esqueleto(altura: 60),
                        SizedBox(height: 10),
                        Esqueleto(altura: 60),
                        SizedBox(height: 10),
                        Esqueleto(altura: 60),
                      ],
                    )
                  else if (_itens.isEmpty)
                    Vazio(
                      titulo: termo.isEmpty ? 'Catálogo vazio.' : 'Nenhum serviço com esse nome.',
                      dica: termo.isEmpty
                          ? 'Os serviços e os preços são cadastrados no painel.'
                          : 'Tente parte do nome — "polimento", "vitrific".',
                      icone: Icons.style_outlined,
                    )
                  else ...[
                    Row(
                      children: [
                        Text(
                          _itens.length == 1 ? '1 serviço' : '${_itens.length} serviços',
                          style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                        ),
                        const Spacer(),
                        Text(
                          'preço de tabela',
                          style: TextStyle(
                            fontSize: 11.5,
                            color: Cores.textoFraco.withValues(alpha: 0.8),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 10),
                    for (final s in _itens) ...[
                      _LinhaServico(
                        servico: s,
                        aberto: _aberto == s.id,
                        aoTocar: () => setState(() => _aberto = _aberto == s.id ? null : s.id),
                      ),
                      const SizedBox(height: 10),
                    ],
                    const SizedBox(height: 6),
                    // O preço combinado de um cliente NÃO aparece aqui de propósito: esta tela
                    // responde "quanto custa", e um valor que vale só para uma pessoa, mostrado
                    // fora da ficha dela, é o caminho curto para cobrar o desconto do outro.
                    const Text(
                      'Preço combinado de cliente e mudanças de tabela ficam no painel.',
                      style: TextStyle(fontSize: 12, color: Cores.textoFraco, height: 1.4),
                    ),
                    const SizedBox(height: 14),
                    OutlinedButton.icon(
                      onPressed: () {
                        setState(() => _mostrarInativos = !_mostrarInativos);
                        _buscar();
                      },
                      icon: Icon(
                        _mostrarInativos ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                        size: 18,
                      ),
                      label: Text(_mostrarInativos ? 'Esconder desativados' : 'Mostrar desativados'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _LinhaServico extends StatelessWidget {
  const _LinhaServico({required this.servico, required this.aberto, required this.aoTocar});

  final Servico servico;
  final bool aberto;
  final VoidCallback aoTocar;

  String get _duracao {
    final min = servico.duracaoMin;
    if (min <= 0) return '';
    if (min < 60) return '$min min';
    final h = min ~/ 60;
    final resto = min % 60;
    return resto == 0 ? '${h}h' : '${h}h${resto.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final temDescricao = (servico.descricao ?? '').trim().isNotEmpty;
    return Material(
      color: Cores.superficie,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: temDescricao ? aoTocar : null,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Cores.linha),
          ),
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          servico.nome,
                          style: TextStyle(
                            fontSize: 15.5,
                            fontWeight: FontWeight.w600,
                            color: servico.ativo ? Cores.texto : Cores.textoFraco,
                          ),
                        ),
                        if (_duracao.isNotEmpty || !servico.ativo || temDescricao) ...[
                          const SizedBox(height: 3),
                          Row(
                            children: [
                              if (_duracao.isNotEmpty)
                                Text(
                                  _duracao,
                                  style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                                ),
                              if (_duracao.isNotEmpty && temDescricao)
                                const Text(
                                  '  ·  ',
                                  style: TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                                ),
                              if (temDescricao)
                                Text(
                                  aberto ? 'ocultar detalhe' : 'ver detalhe',
                                  style: const TextStyle(fontSize: 12.5, color: Cores.ouro),
                                ),
                              if (!servico.ativo) ...[
                                if (_duracao.isNotEmpty || temDescricao)
                                  const Text(
                                    '  ·  ',
                                    style: TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                                  ),
                                const Text(
                                  'fora de linha',
                                  style: TextStyle(fontSize: 12.5, color: Cores.alerta),
                                ),
                              ],
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    reais(servico.valorBaseCentavos),
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                      color: servico.ativo ? Cores.texto : Cores.textoFraco,
                    ),
                  ),
                ],
              ),
              if (aberto && temDescricao) ...[
                const SizedBox(height: 10),
                Container(height: 1, color: Cores.linha),
                const SizedBox(height: 10),
                Text(
                  servico.descricao!.trim(),
                  style: const TextStyle(fontSize: 13.5, color: Cores.textoFraco, height: 1.4),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
