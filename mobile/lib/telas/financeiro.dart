import 'package:flutter/material.dart';

import '../api.dart';
import '../financeiro.dart';
import '../modelos.dart';
import '../tema.dart';
import '../ui.dart';
import 'os.dart';

enum AbaFinanceiro { extrato, cobrancas }

/// Extrato e cobranças no celular — só leitura.
///
/// O sócio confere e cobra; editar preço, desconto e prazo continua sendo do painel. Não é falta
/// de confiança: é que essas edições pedem contexto (tabela de preços, histórico do cliente) que
/// não cabe bem numa tela de balcão, e errar ali mexe em dinheiro.
///
/// Os períodos são presets, não um seletor cheio de opções: no celular, "hoje / 7 dias / este mês"
/// cobre o que se pergunta em pé no pátio.
class TelaFinanceiro extends StatefulWidget {
  const TelaFinanceiro({
    required this.api,
    this.abaInicial = AbaFinanceiro.extrato,
    this.situacaoInicial = 'pendente',
    super.key,
  });

  final Api api;
  final AbaFinanceiro abaInicial;
  final String situacaoInicial;

  @override
  State<TelaFinanceiro> createState() => _TelaFinanceiroState();
}

class _TelaFinanceiroState extends State<TelaFinanceiro> {
  late AbaFinanceiro _aba = widget.abaInicial;
  late String _situacao = widget.situacaoInicial;
  int _preset = 0; // 0 hoje · 1 sete dias · 2 este mês

  Extrato? _extrato;
  List<OS> _cobrancas = const [];
  String? _erro;
  bool _carregando = true;

  static const _presets = ['Hoje', '7 dias', 'Este mês'];

  @override
  void initState() {
    super.initState();
    _buscar();
  }

  ({String de, String ate}) _periodo() {
    final hoje = DateTime.now();
    String d(DateTime x) =>
        '${x.year.toString().padLeft(4, '0')}-${x.month.toString().padLeft(2, '0')}-${x.day.toString().padLeft(2, '0')}';
    return switch (_preset) {
      1 => (de: d(hoje.subtract(const Duration(days: 6))), ate: d(hoje)),
      2 => (de: d(DateTime(hoje.year, hoje.month, 1)), ate: d(hoje)),
      _ => (de: d(hoje), ate: d(hoje)),
    };
  }

  Future<void> _buscar() async {
    setState(() {
      _carregando = true;
      _erro = null;
    });
    try {
      if (_aba == AbaFinanceiro.extrato) {
        final p = _periodo();
        final j = await widget.api.get('/extrato', {'de': p.de, 'ate': p.ate, 'page_size': 100});
        if (!mounted) return;
        setState(() {
          _extrato = Extrato.doJson(j as Map<String, dynamic>);
          _carregando = false;
        });
      } else {
        final j = await widget.api.get('/work-orders', {'cobranca': _situacao, 'page_size': 100});
        if (!mounted) return;
        setState(() {
          _cobrancas = ((j as Map<String, dynamic>)['items'] as List)
              .map((e) => OS.doJson(e as Map<String, dynamic>))
              .toList();
          _carregando = false;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erro = mensagemDeErro(e);
        _carregando = false;
      });
    }
  }

  Future<void> _abrirOS(int id) async {
    await Navigator.of(context).push(MaterialPageRoute<bool>(builder: (_) => TelaOS(api: widget.api, osId: id)));
    if (mounted) await _buscar();
  }

  void _trocarAba(AbaFinanceiro nova) {
    if (nova == _aba) return;
    setState(() => _aba = nova);
    _buscar();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Financeiro')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
            child: SegmentedButton<AbaFinanceiro>(
              segments: const [
                ButtonSegment(value: AbaFinanceiro.extrato, label: Text('Extrato')),
                ButtonSegment(value: AbaFinanceiro.cobrancas, label: Text('Cobranças')),
              ],
              selected: {_aba},
              onSelectionChanged: (s) => _trocarAba(s.first),
              showSelectedIcon: false,
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _buscar,
              child: _aba == AbaFinanceiro.extrato ? _listaExtrato() : _listaCobrancas(),
            ),
          ),
        ],
      ),
    );
  }

  // ------------------------------------------------------------------ extrato

  Widget _listaExtrato() {
    final e = _extrato;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        Wrap(
          spacing: 8,
          children: List.generate(
            _presets.length,
            (i) => ChoiceChip(
              label: Text(_presets[i]),
              selected: _preset == i,
              onSelected: (_) {
                setState(() => _preset = i);
                _buscar();
              },
            ),
          ),
        ),
        const SizedBox(height: 14),
        if (_erro != null) ...[Faixa(_erro!, aoTocar: _buscar, icone: Icons.wifi_off), const SizedBox(height: 14)],
        if (_carregando && e == null)
          const _EsqueletoLista()
        else if (e != null) ...[
          Bloco(
            titulo: e.periodoLabel,
            filhos: [
              Text(
                reais(e.totalCentavos),
                style: const TextStyle(
                  fontSize: 30,
                  fontWeight: FontWeight.w700,
                  height: 1.05,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
              const SizedBox(height: 6),
              Text(
                e.total == 0
                    ? 'Nenhum lançamento no período'
                    : '${e.total} ${e.total == 1 ? "lançamento" : "lançamentos"}',
                style: const TextStyle(fontSize: 13, color: Cores.textoFraco),
              ),
              if (e.porForma.isNotEmpty) ...[
                const SizedBox(height: 12),
                const Divider(height: 1, color: Cores.linha),
                const SizedBox(height: 8),
                for (final f in e.porForma) Linha(f.formaLabel, reais(f.totalCentavos)),
              ],
              // Sem esta linha sobra uma diferença sem nome entre o bruto que se confere na mão e
              // o total que o app mostra.
              if (e.estornosCentavos > 0) ...[
                const SizedBox(height: 8),
                Linha('Estornado no período', reais(e.estornosCentavos), cor: Cores.textoFraco),
              ],
            ],
          ),
          const SizedBox(height: 14),
          if (e.lancamentos.isEmpty)
            const Vazio(
              titulo: 'Nada entrou neste período.',
              dica: 'Pagamento se lança dentro da OS; aqui só se confere.',
              icone: Icons.receipt_long_outlined,
            )
          else
            for (final l in e.lancamentos) _LinhaLancamento(l, aoTocar: () => _abrirOS(l.workOrderId)),
        ],
      ],
    );
  }

  // ---------------------------------------------------------------- cobranças

  Widget _listaCobrancas() {
    const abas = [
      ('pendente', 'A receber'),
      ('atrasado', 'Atrasadas'),
      ('pago', 'Pagas'),
    ];
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
      children: [
        Wrap(
          spacing: 8,
          children: [
            for (final (valor, label) in abas)
              ChoiceChip(
                label: Text(label),
                selected: _situacao == valor,
                onSelected: (_) {
                  setState(() => _situacao = valor);
                  _buscar();
                },
              ),
          ],
        ),
        const SizedBox(height: 14),
        if (_erro != null) ...[Faixa(_erro!, aoTocar: _buscar, icone: Icons.wifi_off), const SizedBox(height: 14)],
        if (_carregando && _cobrancas.isEmpty)
          const _EsqueletoLista()
        else if (_cobrancas.isEmpty)
          Vazio(
            titulo: switch (_situacao) {
              'atrasado' => 'Nenhuma cobrança atrasada — tudo em dia.',
              'pago' => 'Nenhuma OS quitada por aqui ainda.',
              _ => 'Nada em aberto.',
            },
            dica: _situacao == 'atrasado'
                ? 'Carro que sai devendo sem prazo combinado aparece aqui no dia seguinte.'
                : null,
            icone: Icons.verified_outlined,
          )
        else ...[
          Linha(
            'Soma desta lista',
            reais(_cobrancas.fold<int>(0, (s, o) => s + o.saldoCentavos)),
            forte: true,
          ),
          const SizedBox(height: 8),
          for (final os in _cobrancas) _LinhaCobranca(os, aoTocar: () => _abrirOS(os.id)),
        ],
      ],
    );
  }
}

class _LinhaLancamento extends StatelessWidget {
  const _LinhaLancamento(this.l, {required this.aoTocar});
  final Lancamento l;
  final VoidCallback aoTocar;

  @override
  Widget build(BuildContext context) {
    final risco = l.estornado ? TextDecoration.lineThrough : null;
    return InkWell(
      onTap: aoTocar,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: Cores.linha)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${l.clienteNome} · ${l.numeroFormatado}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w600,
                      decoration: risco,
                      color: l.estornado ? Cores.textoFraco : Cores.texto,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    l.estornado
                        ? 'Estornado — ${l.estornoMotivo ?? "sem motivo"}'
                        : '${l.formaLabel} · ${hora(l.pagoEm)}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                  ),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Text(
              reais(l.valorCentavos),
              style: TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w600,
                decoration: risco,
                color: l.estornado ? Cores.textoFraco : Cores.texto,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LinhaCobranca extends StatelessWidget {
  const _LinhaCobranca(this.os, {required this.aoTocar});
  final OS os;
  final VoidCallback aoTocar;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: aoTocar,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
        decoration: const BoxDecoration(
          border: Border(bottom: BorderSide(color: Cores.linha)),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${os.clienteNome} · ${os.numeroFormatado}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    os.veiculo,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco),
                  ),
                  const SizedBox(height: 6),
                  EtiquetaCobranca(os),
                ],
              ),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  reais(os.saldoCentavos),
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: Cores.doTone(os.situacaoCobrancaTone ?? 'neutral'),
                    fontFeatures: const [FontFeature.tabularFigures()],
                  ),
                ),
                if (os.vencimento != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Text(
                      'vence ${data(os.vencimento!)}',
                      style: const TextStyle(fontSize: 11.5, color: Cores.textoFraco),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _EsqueletoLista extends StatelessWidget {
  const _EsqueletoLista();

  @override
  Widget build(BuildContext context) => Column(
        children: List.generate(
          5,
          (_) => const Padding(
            padding: EdgeInsets.symmetric(vertical: 10),
            child: Row(
              children: [
                Expanded(child: Esqueleto(altura: 14)),
                SizedBox(width: 40),
                Esqueleto(altura: 14, largura: 70),
              ],
            ),
          ),
        ),
      );
}
