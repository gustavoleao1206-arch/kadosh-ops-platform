import 'package:flutter/material.dart';

import '../api.dart';
import '../modelos.dart';
import '../tema.dart';
import 'os.dart';

/// O caixa do dia.
///
/// Lançar pagamento é dentro da OS; aqui se confere o dia no fim do expediente: quanto entrou, em
/// quê, e quem saiu devendo. A lista de devedores é tocável de propósito — o cliente que levou o
/// carro devendo e voltou no dia seguinte não aparece mais no pátio, e sem esta porta o sócio não
/// teria como receber dele.
class TelaCaixa extends StatefulWidget {
  const TelaCaixa({required this.api, super.key});
  final Api api;

  @override
  State<TelaCaixa> createState() => _TelaCaixaState();
}

class _TelaCaixaState extends State<TelaCaixa> {
  Map<String, dynamic>? _caixa;
  bool _carregando = true;
  String? _erro;

  @override
  void initState() {
    super.initState();
    _buscar();
  }

  Future<void> _buscar() async {
    try {
      final j = await widget.api.get('/caixa') as Map<String, dynamic>;
      if (mounted) {
        setState(() {
          _caixa = j;
          _erro = null;
          _carregando = false;
        });
      }
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

  Future<void> _abrirOS(int id) async {
    final mudou = await Navigator.of(context).push<bool>(
      MaterialPageRoute(builder: (_) => TelaOS(api: widget.api, osId: id)),
    );
    if (mudou == true) await _buscar();
  }

  @override
  Widget build(BuildContext context) {
    final c = _caixa;
    return Scaffold(
      appBar: AppBar(title: const Text('Caixa de hoje')),
      body: _carregando
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _buscar,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 40),
                children: [
                  if (_erro != null) _Faixa(texto: _erro!),
                  if (c == null)
                    const Text(
                      'Não deu para carregar o caixa.',
                      style: TextStyle(color: Cores.perigo, fontSize: 15),
                    )
                  else
                    ..._corpo(c),
                ],
              ),
            ),
    );
  }

  List<Widget> _corpo(Map<String, dynamic> c) {
    final recebido = c['recebido_centavos'] as int;
    final porForma = (c['por_forma'] as List).cast<Map<String, dynamic>>();
    final lancamentos = (c['lancamentos'] as List).cast<Map<String, dynamic>>();
    final aReceber = c['a_receber_centavos'] as int;
    final devedores = (c['a_receber'] as List).cast<Map<String, dynamic>>();

    return [
      Card(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'ENTROU HOJE',
                style: TextStyle(
                  fontSize: 12.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.4,
                  color: Cores.textoFraco,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                reais(recebido),
                style: const TextStyle(fontSize: 34, fontWeight: FontWeight.w700),
              ),
              if (porForma.isNotEmpty) ...[
                const SizedBox(height: 14),
                for (final f in porForma)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 5),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            f['forma_label'] as String,
                            style: const TextStyle(fontSize: 15, color: Cores.textoFraco),
                          ),
                        ),
                        Text(
                          reais(f['total_centavos'] as int),
                          style: const TextStyle(fontSize: 15),
                        ),
                      ],
                    ),
                  ),
              ],
            ],
          ),
        ),
      ),
      const SizedBox(height: 14),
      _Bloco(
        titulo: 'Lançamentos',
        filhos: lancamentos.isEmpty
            ? const [
                Text(
                  'Nada lançado hoje ainda.',
                  style: TextStyle(fontSize: 14.5, color: Cores.textoFraco),
                ),
              ]
            : [
                for (final l in lancamentos) _LinhaLancamento(l),
              ],
      ),
      if (devedores.isNotEmpty) ...[
        const SizedBox(height: 14),
        _Bloco(
          titulo: 'A receber · ${reais(aReceber)}',
          filhos: [
            for (final d in devedores)
              InkWell(
                onTap: () => _abrirOS(d['work_order_id'] as int),
                borderRadius: BorderRadius.circular(6),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              d['cliente_nome'] as String,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 15),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              d['status_label'] as String,
                              style: const TextStyle(fontSize: 13, color: Cores.textoFraco),
                            ),
                          ],
                        ),
                      ),
                      Text(
                        reais(d['saldo_centavos'] as int),
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                          color: Cores.alerta,
                        ),
                      ),
                      const SizedBox(width: 4),
                      const Icon(Icons.chevron_right, size: 20, color: Cores.textoFraco),
                    ],
                  ),
                ),
              ),
          ],
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

class _LinhaLancamento extends StatelessWidget {
  const _LinhaLancamento(this.l);
  final Map<String, dynamic> l;

  @override
  Widget build(BuildContext context) {
    // Estornado fica na lista, riscado: sumir com ele esconderia justamente o que o dono procura
    // quando o caixa não fecha.
    final estornado = l['estornado_em'] != null;
    final quando = DateTime.parse(l['pago_em'] as String).toLocal();
    final cor = estornado ? Cores.textoFraco : Cores.texto;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  l['cliente_nome'] as String,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(fontSize: 15, color: cor),
                ),
                const SizedBox(height: 2),
                Text(
                  '${l['forma_label']} · ${hora(quando)}${estornado ? ' · estornado' : ''}',
                  style: const TextStyle(fontSize: 13, color: Cores.textoFraco),
                ),
              ],
            ),
          ),
          Text(
            reais(l['valor_centavos'] as int),
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: cor,
              decoration: estornado ? TextDecoration.lineThrough : null,
            ),
          ),
        ],
      ),
    );
  }
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
