import 'package:flutter/material.dart';

import '../api.dart';
import '../modelos.dart';
import '../tema.dart';
import '../ui.dart';
import 'os.dart';

/// Quem chega hoje — e em que hora.
///
/// O pátio responde "o que está na loja agora"; esta tela responde "o que ainda vai chegar", que é
/// a pergunta das 8 da manhã e a que decide se dá para encaixar mais um carro.
///
/// Navega por dia porque a agenda de amanhã é consultada quase tanto quanto a de hoje: o cliente
/// liga perguntando se tem vaga, e a resposta está um toque à frente.
///
/// Só LEITURA. Marcar e remarcar continua no painel — é onde se tem teclado, calendário e a visão
/// da semana inteira; fazer isso no celular, no meio do pátio, é o caminho curto para agendar no
/// dia errado.
class TelaAgenda extends StatefulWidget {
  const TelaAgenda({required this.api, super.key});

  final Api api;

  @override
  State<TelaAgenda> createState() => _TelaAgendaState();
}

class _TelaAgendaState extends State<TelaAgenda> {
  /// O dia é do NEGÓCIO, não do aparelho: `noFusoDaLoja` é a mesma régua que o resto do app usa.
  late DateTime _dia = _soData(noFusoDaLoja(DateTime.now()));
  List<OS> _itens = const [];
  int _noPatio = 0;
  bool _carregando = true;
  String? _erro;

  /// A seta do dia e o alvo de toques em sequencia — o sócio anda três dias para frente antes da
  /// primeira resposta chegar. Sem esta trava, a resposta do dia 12 pinta a tela que já diz 14.
  /// Mesma régua das outras telas de consulta.
  int _geracao = 0;

  static DateTime _soData(DateTime d) => DateTime(d.year, d.month, d.day);

  bool get _ehHoje => _soData(noFusoDaLoja(DateTime.now())) == _dia;

  String get _diaParaApi =>
      '${_dia.year.toString().padLeft(4, '0')}-${_dia.month.toString().padLeft(2, '0')}-${_dia.day.toString().padLeft(2, '0')}';

  String get _tituloDoDia {
    if (_ehHoje) return 'Hoje';
    final amanha = _soData(noFusoDaLoja(DateTime.now()).add(const Duration(days: 1)));
    final ontem = _soData(noFusoDaLoja(DateTime.now()).subtract(const Duration(days: 1)));
    if (_dia == amanha) return 'Amanhã';
    if (_dia == ontem) return 'Ontem';
    const semana = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];
    return semana[_dia.weekday - 1];
  }

  @override
  void initState() {
    super.initState();
    _buscar();
  }

  Future<void> _buscar() async {
    final minha = ++_geracao;
    setState(() {
      _carregando = true;
      _erro = null;
    });
    try {
      final j = await widget.api.get('/agenda', {'dia': _diaParaApi}) as Map<String, dynamic>;
      if (!mounted || minha != _geracao) return;
      final resumo = (j['resumo'] as Map<String, dynamic>?) ?? const {};
      setState(() {
        _itens = ((j['itens'] as List?) ?? const [])
            .map((e) => OS.doJson(e as Map<String, dynamic>))
            .toList();
        _noPatio = (resumo['no_patio'] as int?) ?? 0;
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

  void _mover(int dias) {
    setState(() => _dia = _soData(_dia.add(Duration(days: dias))));
    _buscar();
  }

  Future<void> _abrirOS(OS os) async {
    await Navigator.of(context).push(
      MaterialPageRoute<bool>(builder: (_) => TelaOS(api: widget.api, osId: os.id)),
    );
    if (mounted) await _buscar();
  }

  @override
  Widget build(BuildContext context) {
    // A agenda do dia inclui carro que já está no pátio (ele aparece todo dia até sair, por decisão
    // do servidor). Separar os dois faz a tela responder a pergunta certa: "quem falta chegar" é o
    // que se conta de manhã.
    final aguardando = _itens.where((o) => o.status == 'agendado' || o.status == 'confirmado').toList();
    final naLoja = _itens.where((o) => o.status != 'agendado' && o.status != 'confirmado').toList();

    // Os rótulos mudam com o dia porque senão mentem. Num dia que já passou, "a chegar" descreve
    // gente que não chega mais; e o carro do pátio aparece ali porque está na loja AGORA, não
    // porque estava naquele dia — por isso este bloco nunca fala no passado.
    final passado = _dia.isBefore(_soData(noFusoDaLoja(DateTime.now())));

    return Scaffold(
      appBar: AppBar(title: const Text('Agenda')),
      body: RefreshIndicator(
        onRefresh: _buscar,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
          children: [
            _Navegador(
              titulo: _tituloDoDia,
              data: '${_dia.day.toString().padLeft(2, '0')}/${_dia.month.toString().padLeft(2, '0')}',
              ehHoje: _ehHoje,
              aoVoltar: () => _mover(-1),
              aoAvancar: () => _mover(1),
              aoHoje: () {
                setState(() => _dia = _soData(noFusoDaLoja(DateTime.now())));
                _buscar();
              },
            ),
            const SizedBox(height: 16),

            if (_erro != null) ...[
              Faixa(_erro!, aoTocar: _buscar, icone: Icons.wifi_off),
              const SizedBox(height: 16),
            ],

            if (_carregando && _itens.isEmpty)
              const Column(
                children: [
                  Esqueleto(altura: 76),
                  SizedBox(height: 10),
                  Esqueleto(altura: 76),
                ],
              )
            else ...[
              Row(
                children: [
                  Expanded(
                    child: CartaoNumero(
                      rotulo: passado ? 'Marcados' : 'Chegam',
                      valor: '${aguardando.length}',
                      detalhe: aguardando.isEmpty ? 'nada marcado' : 'agendados e confirmados',
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: CartaoNumero(
                      rotulo: 'Na loja agora',
                      valor: '$_noPatio',
                      detalhe: _noPatio == 0 ? 'pátio vazio' : 'em qualquer dia',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 22),

              if (aguardando.isEmpty && naLoja.isEmpty)
                Vazio(
                  titulo: _ehHoje ? 'Nada marcado para hoje.' : 'Nada marcado para este dia.',
                  dica: 'Agendamento se faz no painel. O carro que chega sem marcar entra por "Receber veículo".',
                  icone: Icons.event_available_outlined,
                )
              else ...[
                if (aguardando.isNotEmpty) ...[
                  Rotulo(passado ? 'Estavam marcados' : 'A chegar'),
                  const SizedBox(height: 10),
                  for (final os in aguardando) ...[
                    _LinhaAgenda(os: os, aoTocar: () => _abrirOS(os)),
                    const SizedBox(height: 10),
                  ],
                ],
                if (naLoja.isNotEmpty) ...[
                  if (aguardando.isNotEmpty) const SizedBox(height: 12),
                  const Rotulo('Na loja agora'),
                  const SizedBox(height: 10),
                  for (final os in naLoja) ...[
                    _LinhaAgenda(os: os, aoTocar: () => _abrirOS(os)),
                    const SizedBox(height: 10),
                  ],
                ],
              ],
            ],
          ],
        ),
      ),
    );
  }
}

class _Navegador extends StatelessWidget {
  const _Navegador({
    required this.titulo,
    required this.data,
    required this.ehHoje,
    required this.aoVoltar,
    required this.aoAvancar,
    required this.aoHoje,
  });

  final String titulo;
  final String data;
  final bool ehHoje;
  final VoidCallback aoVoltar;
  final VoidCallback aoAvancar;
  final VoidCallback aoHoje;

  @override
  Widget build(BuildContext context) => Row(
        children: [
          // 48dp de alvo: o polegar erra seta pequena, e errar aqui troca o dia inteiro
          IconButton(
            onPressed: aoVoltar,
            icon: const Icon(Icons.chevron_left),
            tooltip: 'Dia anterior',
            iconSize: 28,
          ),
          Expanded(
            child: Column(
              children: [
                Text(titulo, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w600)),
                Text(data, style: const TextStyle(fontSize: 13, color: Cores.textoFraco)),
              ],
            ),
          ),
          IconButton(
            onPressed: aoAvancar,
            icon: const Icon(Icons.chevron_right),
            tooltip: 'Próximo dia',
            iconSize: 28,
          ),
          if (!ehHoje)
            TextButton(onPressed: aoHoje, child: const Text('Hoje')),
        ],
      );
}

class _LinhaAgenda extends StatelessWidget {
  const _LinhaAgenda({required this.os, required this.aoTocar});

  final OS os;
  final VoidCallback aoTocar;

  @override
  Widget build(BuildContext context) {
    final marcado = os.agendadoPara ?? os.entrada;
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
              // A hora à esquerda, grande: quem lê a agenda lê primeiro a hora, e o resto só
              // depois de decidir que aquela linha interessa.
              SizedBox(
                width: 58,
                child: Text(
                  marcado == null ? '—' : hora(marcado),
                  style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w700, height: 1.1),
                ),
              ),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      os.clienteNome,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      os.veiculo.isEmpty
                          ? 'sem veículo definido'
                          : '${os.veiculo} · ${placaFormatada(os.placa)}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 13.5, color: Cores.textoFraco),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Etiqueta(os.statusLabel, tone: os.statusTone),
            ],
          ),
        ),
      ),
    );
  }
}
