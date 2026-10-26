import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api.dart';
import '../modelos.dart';
import '../tema.dart';
import '../ui.dart';
import 'os.dart';

/// Consulta de clientes: achar a pessoa, achar o telefone, ver o que ela já fez aqui.
///
/// O balcão faz três perguntas sobre cliente, e nenhuma delas é "quero cadastrar": qual é o
/// telefone, esse carro é de quem, e quanto essa pessoa já gastou na loja. Cliente novo entra por
/// "Receber veículo", que abre cliente, veículo e OS numa transação só — duplicar isso aqui criaria
/// um segundo jeito de nascer cliente, e é assim que aparece cadastro repetido.
///
/// Corrigir cadastro (nome errado, telefone trocado) segue no painel, com teclado de verdade.
class TelaClientes extends StatefulWidget {
  const TelaClientes({required this.api, super.key});

  final Api api;

  @override
  State<TelaClientes> createState() => _TelaClientesState();
}

class _TelaClientesState extends State<TelaClientes> {
  final _busca = TextEditingController();
  Timer? _debounce;

  List<Cliente> _itens = const [];
  int _total = 0;
  int _pagina = 1;
  bool _carregando = true;
  bool _carregandoMais = false;
  String? _erro;

  /// Cada busca leva um número, e só a resposta do número atual pinta a tela. Sem isto, uma busca
  /// lenta por "jo" chega depois da busca por "joão" e devolve a lista errada — no balcão isso
  /// parece defeito de dados, não de rede.
  int _geracao = 0;

  static const _porPagina = 40;

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
    setState(() {}); // o "x" de limpar aparece e some junto com o texto
    _debounce?.cancel();
    // 350ms: menos que isso dispara uma requisição por letra; mais que isso a lista parece travada
    _debounce = Timer(const Duration(milliseconds: 350), _buscar);
  }

  Future<void> _buscar() async {
    final minha = ++_geracao;
    setState(() {
      _carregando = true;
      _erro = null;
      _pagina = 1;
    });
    try {
      final j = await _pagar(1);
      if (!mounted || minha != _geracao) return;
      setState(() {
        _itens = _lista(j);
        _total = (j['total'] as int?) ?? 0;
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

  Future<void> _mais() async {
    if (_carregandoMais) return;
    final minha = _geracao;
    setState(() => _carregandoMais = true);
    try {
      final j = await _pagar(_pagina + 1);
      if (!mounted || minha != _geracao) return;
      setState(() {
        _itens = [..._itens, ..._lista(j)];
        _pagina += 1;
        _carregandoMais = false;
      });
    } catch (e) {
      if (!mounted || minha != _geracao) return;
      setState(() {
        _erro = mensagemDeErro(e);
        _carregandoMais = false;
      });
    }
  }

  Future<Map<String, dynamic>> _pagar(int pagina) async {
    final termo = _busca.text.trim();
    final j = await widget.api.get('/clients', {
      if (termo.isNotEmpty) 'q': termo,
      'page': pagina,
      'page_size': _porPagina,
    });
    return j as Map<String, dynamic>;
  }

  List<Cliente> _lista(Map<String, dynamic> j) =>
      ((j['items'] as List?) ?? const []).map((c) => Cliente.doJson(c as Map<String, dynamic>)).toList();

  @override
  Widget build(BuildContext context) {
    final termo = _busca.text.trim();
    final faltam = _total - _itens.length;

    return Scaffold(
      appBar: AppBar(title: const Text('Clientes')),
      body: Column(
        children: [
          // A busca fica FORA da lista que rola: com o teclado aberto e a lista subindo, um campo
          // que rola junto some na hora em que a pessoa ainda está digitando.
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: TextField(
              controller: _busca,
              onChanged: _aoDigitar,
              textInputAction: TextInputAction.search,
              onSubmitted: (_) => _buscar(),
              decoration: InputDecoration(
                hintText: 'Nome, telefone ou placa',
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
                        Esqueleto(altura: 68),
                        SizedBox(height: 10),
                        Esqueleto(altura: 68),
                        SizedBox(height: 10),
                        Esqueleto(altura: 68),
                      ],
                    )
                  else if (_itens.isEmpty)
                    Vazio(
                      titulo: termo.isEmpty ? 'Nenhum cliente cadastrado ainda.' : 'Ninguém encontrado.',
                      dica: termo.isEmpty
                          ? 'O primeiro cliente nasce quando você recebe o primeiro veículo.'
                          : 'A busca olha nome, telefone e placa. Confira se o termo está certo.',
                      icone: Icons.person_search_outlined,
                    )
                  else ...[
                    Text(
                      _total == 1 ? '1 cliente' : '$_total clientes',
                      style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                    ),
                    const SizedBox(height: 10),
                    for (final c in _itens) ...[
                      _LinhaCliente(
                        cliente: c,
                        aoTocar: () => Navigator.of(context).push(
                          MaterialPageRoute<void>(
                            builder: (_) => TelaCliente(api: widget.api, clienteId: c.id),
                          ),
                        ),
                      ),
                      const SizedBox(height: 10),
                    ],
                    if (faltam > 0)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: OutlinedButton(
                          onPressed: _carregandoMais ? null : _mais,
                          child: Text(_carregandoMais ? 'Carregando...' : 'Mostrar mais $faltam'),
                        ),
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

class _LinhaCliente extends StatelessWidget {
  const _LinhaCliente({required this.cliente, required this.aoTocar});

  final Cliente cliente;
  final VoidCallback aoTocar;

  @override
  Widget build(BuildContext context) {
    final carros = cliente.veiculos.map((v) => v.descricao).where((d) => d.isNotEmpty).join(', ');
    return Material(
      color: Cores.superficie,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: aoTocar,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Cores.linha),
          ),
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            cliente.nome,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 15.5, fontWeight: FontWeight.w600),
                          ),
                        ),
                        if (cliente.arquivado) ...[
                          const SizedBox(width: 8),
                          const Etiqueta('arquivado', tone: 'muted'),
                        ],
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      telefoneFormatado(cliente.telefone),
                      style: const TextStyle(fontSize: 13.5, color: Cores.textoFraco),
                    ),
                    if (carros.isNotEmpty) ...[
                      const SizedBox(height: 2),
                      Text(
                        carros,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                      ),
                    ],
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: Cores.textoFraco),
            ],
          ),
        ),
      ),
    );
  }
}

/// A ficha: como falar com a pessoa, o que ela já gastou e por onde os carros dela passaram.
class TelaCliente extends StatefulWidget {
  const TelaCliente({required this.api, required this.clienteId, super.key});

  final Api api;
  final int clienteId;

  @override
  State<TelaCliente> createState() => _TelaClienteState();
}

class _TelaClienteState extends State<TelaCliente> {
  ClienteFicha? _ficha;
  bool _carregando = true;
  String? _erro;

  @override
  void initState() {
    super.initState();
    _buscar();
  }

  Future<void> _buscar() async {
    setState(() {
      _carregando = true;
      _erro = null;
    });
    try {
      final j = await widget.api.get('/clients/${widget.clienteId}') as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _ficha = ClienteFicha.doJson(j);
        _carregando = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erro = mensagemDeErro(e);
        _carregando = false;
      });
    }
  }

  void _aviso(String texto) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(texto), backgroundColor: Cores.perigo));
  }

  Future<void> _abrirLink(Uri url, String oQue) async {
    try {
      final abriu = await launchUrl(url, mode: LaunchMode.externalApplication);
      if (!abriu && mounted) _aviso('Não deu para abrir o $oQue.');
    } catch (_) {
      // sem o app instalado o plugin lança em vez de devolver false
      if (mounted) _aviso('Não deu para abrir o $oQue.');
    }
  }

  @override
  Widget build(BuildContext context) {
    final f = _ficha;
    final fone = f?.cliente.telefone;
    final temFone = fone != null && fone.trim().isNotEmpty;

    return Scaffold(
      appBar: AppBar(title: Text(f == null ? 'Cliente' : primeiroNome(f.cliente.nome))),
      body: RefreshIndicator(
        onRefresh: _buscar,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 32),
          children: [
            if (_erro != null) ...[
              Faixa(_erro!, aoTocar: _buscar, icone: Icons.wifi_off),
              const SizedBox(height: 14),
            ],
            if (_carregando && f == null)
              const Column(
                children: [
                  Esqueleto(altura: 90),
                  SizedBox(height: 12),
                  Esqueleto(altura: 120),
                ],
              )
            else if (f != null) ...[
              Text(
                f.cliente.nome,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600, height: 1.15),
              ),
              const SizedBox(height: 4),
              Text(
                telefoneFormatado(f.cliente.telefone),
                style: const TextStyle(fontSize: 14.5, color: Cores.textoFraco),
              ),
              const SizedBox(height: 16),

              // Contato antes dos números: a ficha quase sempre é aberta para falar com a pessoa.
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: temFone ? () => _abrirLink(Uri.parse('https://wa.me/$fone'), 'WhatsApp') : null,
                      icon: const Icon(Icons.chat_outlined, size: 18),
                      label: const Text('WhatsApp'),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: temFone ? () => _abrirLink(Uri.parse('tel:$fone'), 'telefone') : null,
                      icon: const Icon(Icons.call_outlined, size: 18),
                      label: const Text('Ligar'),
                    ),
                  ),
                ],
              ),
              if (!temFone) ...[
                const SizedBox(height: 8),
                const Text(
                  'Sem telefone cadastrado — quem corrige é o painel.',
                  style: TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                ),
              ],
              const SizedBox(height: 20),

              Row(
                children: [
                  Expanded(
                    child: CartaoNumero(
                      rotulo: 'Atendimentos',
                      valor: '${f.atendimentos}',
                      detalhe: f.ultimoAtendimento == null
                          ? 'nenhum concluído'
                          : 'último em ${dataCompleta(f.ultimoAtendimento!)}',
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: CartaoNumero(
                      rotulo: 'Já gastou',
                      valor: reais(f.totalGastoCentavos),
                      // "em OS entregues" não é enfeite: o servidor só conta OS concluída, e sem
                      // dizer isso o card mostra R$ 0,00 ao lado de um histórico cheio de valores.
                      detalhe: 'em OS entregues',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 22),

              if (f.cliente.veiculos.isNotEmpty) ...[
                Bloco(
                  titulo: f.cliente.veiculos.length == 1 ? 'Veículo' : 'Veículos',
                  filhos: [
                    for (final v in f.cliente.veiculos)
                      Linha(v.descricao.isEmpty ? 'Sem modelo' : v.descricao, placaFormatada(v.placa)),
                  ],
                ),
                const SizedBox(height: 22),
              ],

              const Rotulo('Histórico'),
              const SizedBox(height: 10),
              if (f.historico.isEmpty)
                const Vazio(
                  titulo: 'Nenhuma OS ainda.',
                  dica: 'Quando o primeiro carro desta pessoa passar por aqui, ele aparece nesta lista.',
                  icone: Icons.history,
                )
              else
                for (final os in f.historico) ...[
                  _LinhaHistorico(os: os, aoTocar: () => _abrirOS(os)),
                  const SizedBox(height: 10),
                ],
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _abrirOS(OSResumo os) async {
    await Navigator.of(context).push(
      MaterialPageRoute<bool>(builder: (_) => TelaOS(api: widget.api, osId: os.id)),
    );
    // a OS pode ter sido concluída ou paga lá dentro: os números da ficha mudam junto
    if (mounted) await _buscar();
  }
}

class _LinhaHistorico extends StatelessWidget {
  const _LinhaHistorico({required this.os, required this.aoTocar});

  final OSResumo os;
  final VoidCallback aoTocar;

  @override
  Widget build(BuildContext context) {
    final quando = os.quando;
    // O status vem PRIMEIRO: o `veiculo` do resumo já traz marca, modelo, cor e placa, e numa
    // linha de celular ele empurra o que sobra para fora da tela. O que não pode sumir é em que
    // ponto aquela OS parou.
    final detalhe = [
      os.statusLabel,
      if ((os.veiculo ?? '').isNotEmpty) os.veiculo!,
    ].where((s) => s.isNotEmpty).join(' · ');

    return Material(
      color: Cores.superficie,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        onTap: aoTocar,
        borderRadius: BorderRadius.circular(10),
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: Cores.linha),
          ),
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          os.numeroFormatado,
                          style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
                        ),
                        if (quando != null) ...[
                          const SizedBox(width: 8),
                          Text(
                            dataCompleta(quando),
                            style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 3),
                    Text(
                      detalhe,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 13, color: Cores.textoFraco),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Text(
                reais(os.valorTotalCentavos),
                style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
