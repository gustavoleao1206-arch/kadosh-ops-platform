import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../api.dart';
import '../mensagens.dart';
import '../modelos.dart';
import '../tema.dart';
import 'caixa.dart';
import 'os.dart';
import 'receber.dart';

/// O pátio: a tela que o sócio abre dezenas de vezes por dia.
///
/// Uma coluna só, três grupos, placa em destaque e o botão do próximo passo dentro do card. Sem
/// arrastar, sem segurar: uma mão molhada segurando o celular não faz gesto fino.
class TelaPatio extends StatefulWidget {
  const TelaPatio({required this.api, required this.aoSair, this.comoRaiz = true, super.key});
  final Api api;
  final Future<void> Function() aoSair;
  /// false quando o pátio é aberto a partir do Início: aí quem sai do app é a tela inicial, e
  /// esta ganha o botão de voltar em vez do de sair.
  final bool comoRaiz;

  @override
  State<TelaPatio> createState() => _TelaPatioState();
}

class _TelaPatioState extends State<TelaPatio> {
  static const _grupos = [
    ('recebido', 'Recebidos'),
    ('em_execucao', 'Em execução'),
    ('aguardando_retirada', 'Prontos'),
  ];

  Map<String, List<OS>> _patio = const {};
  bool _carregando = true;
  String? _erro;

  /// Um alvo por vez. Sem isto, dois toques rápidos no mesmo card mandam duas transições, e dois
  /// toques no FAB abrem duas telas de recepção — cada uma com sua chave, que é justamente o
  /// caso que a idempotência não cobre.
  bool _ocupado = false;

  @override
  void initState() {
    super.initState();
    _buscar();
  }

  Future<void> _buscar() async {
    try {
      final j = await widget.api.get('/patio') as Map<String, dynamic>;
      final mapa = <String, List<OS>>{};
      for (final (chave, _) in _grupos) {
        mapa[chave] = ((j[chave] as List?) ?? const [])
            .map((e) => OS.doJson(e as Map<String, dynamic>))
            .toList();
      }
      if (mounted) {
        setState(() {
          _patio = mapa;
          _erro = null;
          _carregando = false;
        });
      }
    } on ErroApi catch (e) {
      // 401 já foi tratado pelo Api (volta para o login); aqui só sobra o que dá para mostrar
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

  /// Um toque muda o status. Sem diálogo de confirmação: o desfazer fica na barra que aparece
  /// depois, que é mais rápido de usar e não atrapalha quem acertou.
  Future<void> _mudarStatus(OS os, Acao acao) async {
    if (_ocupado) return;
    // Concluir com saldo em aberto continua permitido — é decisão da loja — mas não em silêncio:
    // é a última ação do carro no dia, e depois dela o sócio não consegue reabrir a OS.
    if (acao.status == 'concluido' && os.aceitaPagamento && os.saldoCentavos > 0) {
      final seguir = await _confirmar(
        'Entregar devendo?',
        '${placaFormatada(os.placa)} ainda tem ${reais(os.saldoCentavos)} em aberto. '
            'Depois de concluir, só o dono reabre esta OS.',
        'Entregar assim mesmo',
      );
      if (seguir != true) return;
    }
    if (acao.requerMotivo) {
      // hoje nenhum passo principal pede motivo, mas quem desenhar um novo não descobre por 422
      _aviso('${acao.acaoLabel} precisa de motivo — abra a OS.', erro: true);
      return;
    }

    setState(() => _ocupado = true);
    final anterior = os.status;
    try {
      final resposta = await widget.api.post(
        '/work-orders/${os.id}/transition',
        {'to_status': acao.status, 'expected_status': anterior},
      );
      if (!mounted) return;
      _aviso(
        '${placaFormatada(os.placa)} · ${acao.label}',
        desfazer: _voltaOferecida(resposta, anterior) ? () => _desfazer(os, anterior, acao.status) : null,
      );
      await _buscar();
    } on ErroApi catch (e) {
      // Rede ruim: o toque anterior pode ter chegado. Antes de gritar erro vermelho, confere.
      if (e.talvezJaFeito && await _jaEsta(os.id, acao.status)) {
        if (!mounted) return;
        _aviso('${placaFormatada(os.placa)} · ${acao.label}');
        await _buscar();
        return;
      }
      if (mounted) _aviso(e.mensagem, erro: true);
    } catch (_) {
      if (mounted) _aviso('Sem conexão. O carro não mudou de status.', erro: true);
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  /// O "Desfazer" só aparece se a API oferecer a volta — e sem pedir motivo.
  ///
  /// Antes ele aparecia sempre, e na ação mais consequente do dia ("Concluir e entregar") era
  /// garantido falhar: reabrir OS concluída é só do administrador, e ainda exige motivo. O sócio
  /// tocava e levava vermelho com o carro já entregue.
  bool _voltaOferecida(dynamic resposta, String paraOnde) {
    if (resposta is! Map<String, dynamic>) return false;
    for (final a in (resposta['acoes'] as List?) ?? const []) {
      final acao = a as Map<String, dynamic>;
      if (acao['status'] == paraOnde) return acao['requer_motivo'] != true;
    }
    return false;
  }

  Future<bool> _jaEsta(int id, String status) async {
    try {
      final j = await widget.api.get('/work-orders/$id') as Map<String, dynamic>;
      return j['status'] == status;
    } catch (_) {
      return false;
    }
  }

  Future<void> _desfazer(OS os, String paraOnde, String deOnde) async {
    try {
      // `expected_status` também na volta: nos 6 segundos do aviso a OS pode ter mudado no painel
      await widget.api.post(
        '/work-orders/${os.id}/transition',
        {'to_status': paraOnde, 'expected_status': deOnde},
      );
      await _buscar();
    } on ErroApi catch (e) {
      if (mounted) _aviso(e.mensagem, erro: true);
    } catch (_) {
      // sem este ramo a falha de rede sumia sem deixar rastro, e o sócio achava que tinha desfeito
      if (mounted) _aviso('Sem conexão. Não deu para desfazer.', erro: true);
    }
  }

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

  void _aviso(String texto, {bool erro = false, VoidCallback? desfazer}) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(
        SnackBar(
          content: Text(texto, style: const TextStyle(fontSize: 15)),
          backgroundColor: erro ? Cores.perigo : Cores.ok,
          duration: Duration(seconds: desfazer != null ? 6 : 3),
          action: desfazer == null
              ? null
              : SnackBarAction(label: 'Desfazer', textColor: Colors.white, onPressed: desfazer),
        ),
      );
  }

  Future<void> _whatsapp(OS os) async {
    final fone = os.clienteTelefone;
    if (fone == null || fone.trim().isEmpty) {
      _aviso('Este cliente não tem telefone cadastrado.', erro: true);
      return;
    }
    // o backend guarda só dígitos com DDI (55 + DDD + número), que é o formato do wa.me
    final url = Uri.parse('https://wa.me/$fone?text=${Uri.encodeComponent(textoPronto(os))}');
    try {
      final abriu = await launchUrl(url, mode: LaunchMode.externalApplication);
      if (!abriu && mounted) _aviso('Não deu para abrir o WhatsApp.', erro: true);
    } catch (_) {
      // sem WhatsApp instalado o plugin lança em vez de devolver false
      if (mounted) _aviso('Não deu para abrir o WhatsApp.', erro: true);
    }
  }

  Future<void> _abrir(Widget Function() tela, {bool recarregaSempre = false}) async {
    if (_ocupado) return;
    setState(() => _ocupado = true);
    try {
      final mudou = await Navigator.of(context).push<bool>(
        MaterialPageRoute(builder: (_) => tela()),
      );
      if (mudou == true || recarregaSempre) await _buscar();
    } finally {
      if (mounted) setState(() => _ocupado = false);
    }
  }

  int get _total => _patio.values.fold(0, (s, l) => s + l.length);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('No pátio'),
        actions: [
          IconButton(
            onPressed: () => _abrir(() => TelaCaixa(api: widget.api)),
            icon: const Icon(Icons.payments_outlined),
            tooltip: 'Caixa de hoje',
          ),
          // O botão de sair só existe quando o pátio É a raiz. Aberto a partir do Início, sair
          // daqui deixaria a pilha de navegação apontando para uma tela de sessão morta.
          if (widget.comoRaiz)
            IconButton(
              onPressed: () async {
                // vizinho do ícone do caixa: errar o alvo derrubaria a sessão e obrigaria a digitar
                // e-mail e senha com a mão molhada
                final sair = await _confirmar('Sair da conta?', 'Você vai precisar entrar de novo.', 'Sair');
                if (sair == true) await widget.aoSair();
              },
              icon: const Icon(Icons.logout),
              tooltip: 'Sair',
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _abrir(() => TelaReceber(api: widget.api)),
        backgroundColor: Cores.ouro,
        foregroundColor: Cores.obsidiana,
        icon: const Icon(Icons.add),
        label: const Text('Receber', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
      ),
      body: RefreshIndicator(
        onRefresh: _buscar,
        child: _carregando
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                // Sem isto o gesto de puxar não é aceito quando o conteúdo cabe na tela — que é
                // exatamente o caso do pátio vazio e o da faixa de erro, onde a própria tela
                // manda puxar para tentar de novo.
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(14, 14, 14, 96),
                children: [
                  if (_erro != null) _Faixa(texto: _erro!),
                  if (_total == 0 && _erro == null)
                    const Padding(
                      padding: EdgeInsets.only(top: 80),
                      child: Center(
                        child: Text(
                          'Nenhum carro na loja agora.',
                          style: TextStyle(color: Cores.textoFraco, fontSize: 16),
                        ),
                      ),
                    ),
                  for (final (chave, titulo) in _grupos) ...[
                    if ((_patio[chave] ?? const []).isNotEmpty) ...[
                      _Cabecalho(titulo: titulo, quantos: _patio[chave]!.length),
                      for (final os in _patio[chave]!)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _CardCarro(
                            os: os,
                            travado: _ocupado,
                            aoMudarStatus: (acao) => _mudarStatus(os, acao),
                            aoAbrir: () => _abrir(() => TelaOS(api: widget.api, osId: os.id)),
                            aoAvisar: os.status == 'aguardando_retirada' ? () => _whatsapp(os) : null,
                          ),
                        ),
                    ],
                  ],
                ],
              ),
      ),
    );
  }
}

class _Cabecalho extends StatelessWidget {
  const _Cabecalho({required this.titulo, required this.quantos});
  final String titulo;
  final int quantos;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 10, top: 6),
        child: Row(
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
            const SizedBox(width: 8),
            Text('$quantos', style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco)),
          ],
        ),
      );
}

class _Faixa extends StatelessWidget {
  const _Faixa({required this.texto});
  final String texto;

  @override
  Widget build(BuildContext context) => Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Cores.perigo.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Cores.perigo.withValues(alpha: 0.3)),
        ),
        child: Text(texto, style: const TextStyle(color: Cores.perigo, fontSize: 14.5)),
      );
}

class _CardCarro extends StatelessWidget {
  const _CardCarro({
    required this.os,
    required this.travado,
    required this.aoMudarStatus,
    required this.aoAbrir,
    this.aoAvisar,
  });

  final OS os;
  final bool travado;
  final void Function(Acao) aoMudarStatus;
  final VoidCallback aoAbrir;
  final VoidCallback? aoAvisar;

  @override
  Widget build(BuildContext context) {
    final principal = os.acaoPrincipal;
    return Card(
      child: InkWell(
        onTap: travado ? null : aoAbrir,
        borderRadius: BorderRadius.circular(10),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  // a placa é o que o sócio procura de longe, no meio do pátio
                  Expanded(
                    child: Text(
                      placaFormatada(os.placa),
                      style: const TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.5,
                      ),
                    ),
                  ),
                  if (os.atrasado)
                    const Etiqueta('atrasado', tone: 'danger')
                  else if (os.previsaoConclusao != null)
                    Text(
                      'até ${hora(os.previsaoConclusao)}',
                      style: const TextStyle(color: Cores.textoFraco, fontSize: 13.5),
                    ),
                ],
              ),
              const SizedBox(height: 2),
              Text(
                '${os.veiculo} · ${os.clienteNome}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 15, color: Cores.texto),
              ),
              if (os.itens.isEmpty)
                const Padding(
                  padding: EdgeInsets.only(top: 3),
                  child: Text(
                    'sem serviço lançado',
                    style: TextStyle(fontSize: 13.5, color: Cores.alerta),
                  ),
                )
              else
                Padding(
                  padding: const EdgeInsets.only(top: 3),
                  child: Text(
                    os.itens.map((i) => i.descricao).join(', '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 13.5, color: Cores.textoFraco),
                  ),
                ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Etiqueta(os.statusLabel, tone: os.statusTone),
                  const Spacer(),
                  // o que decide se o carro pode sair: pelo `aceita_pagamento`, nunca pelo sinal
                  // do saldo, e grande o bastante para ser lido sob sol
                  if (os.aceitaPagamento && os.saldoCentavos > 0)
                    Text(
                      'falta ${reais(os.saldoCentavos)}',
                      style: const TextStyle(
                        fontSize: 16,
                        color: Cores.alerta,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                ],
              ),
              // Avisar vem antes de concluir: quando o carro fica pronto, a ação do momento é
              // chamar o cliente; concluir acontece horas depois, quando ele aparece.
              if (aoAvisar != null) ...[
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: travado ? null : aoAvisar,
                  icon: const Icon(Icons.chat_outlined, size: 20),
                  label: const Text('Avisar no WhatsApp'),
                ),
              ],
              if (principal != null) ...[
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: travado ? null : () => aoMudarStatus(principal),
                  child: Text(principal.acaoLabel),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
