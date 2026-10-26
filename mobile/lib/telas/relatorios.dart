import 'package:flutter/material.dart';

import '../api.dart';
import '../financeiro.dart';
import '../modelos.dart';
import '../tema.dart';
import '../ui.dart';

/// Os números fechados de um mês — e como esse mês se compara aos onze anteriores.
///
/// O painel tem o relatório inteiro (dia da semana, período personalizado, clientes sumidos). Aqui
/// fica o que se pergunta de pé no pátio: quanto a loja fez, quanto entrou, quantos carros saíram,
/// e o que mais deu dinheiro.
///
/// FATURADO e RECEBIDO são contas diferentes e nunca se somam. Faturado é serviço entregue;
/// recebido é dinheiro que entrou na janela. Quem paga o sinal em agosto e leva o carro em setembro
/// aparece nos dois lados, em meses diferentes — e a tela diz isso em vez de deixar a conta "não
/// fechar" na cabeça de quem lê.
///
/// A escolha do mês é o próprio gráfico: tocar numa barra troca o período. Um seletor separado
/// seria mais um lugar para procurar a mesma coisa.
class TelaRelatorios extends StatefulWidget {
  const TelaRelatorios({required this.api, super.key});

  final Api api;

  @override
  State<TelaRelatorios> createState() => _TelaRelatoriosState();
}

class _TelaRelatoriosState extends State<TelaRelatorios> {
  Relatorio? _rel;
  List<MesDoRelatorio> _meses = const [];

  /// null = mês corrente (`periodo=mes`). Preenchido = "2026-08", via `periodo=mes_especifico`.
  String? _mesEscolhido;

  bool _carregando = true;
  String? _erro;
  int _geracao = 0;

  @override
  void initState() {
    super.initState();
    _buscar();
    _buscarSerie();
  }

  Future<void> _buscar() async {
    final minha = ++_geracao;
    setState(() {
      _carregando = true;
      _erro = null;
    });
    try {
      final mes = _mesEscolhido;
      final j = await widget.api.get('/relatorios', {
        'periodo': mes == null ? 'mes' : 'mes_especifico',
        'mes': ?mes,
      }) as Map<String, dynamic>;
      if (!mounted || minha != _geracao) return;
      setState(() {
        _rel = Relatorio.doJson(j);
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

  /// A série é buscada uma vez e não reaparece a cada troca de mês: ela não muda quando se olha
  /// outro mês, e refazer a consulta faria o gráfico piscar a cada toque.
  Future<void> _buscarSerie() async {
    try {
      final j = await widget.api.get('/relatorios/mensal', {'meses': 12}) as Map<String, dynamic>;
      if (!mounted) return;
      setState(() {
        _meses = ((j['meses'] as List?) ?? const [])
            .map((m) => MesDoRelatorio.doJson(m as Map<String, dynamic>))
            .toList();
      });
    } catch (_) {
      // O gráfico é acessório: se ele falhar, os números do mês continuam valendo e a tela não
      // pode virar um erro por causa da faixa de baixo.
    }
  }

  Future<void> _recarregar() async {
    await Future.wait([_buscar(), _buscarSerie()]);
  }

  void _escolher(MesDoRelatorio m) {
    // O último mês da série é o corrente: escolhê-lo volta para `periodo=mes`, que é o que a tela
    // abre — assim não existem dois caminhos para o mesmo período.
    final ehCorrente = _meses.isNotEmpty && _meses.last.mes == m.mes;
    setState(() => _mesEscolhido = ehCorrente ? null : m.mes);
    _buscar();
  }

  String? get _mesAtivo => _mesEscolhido ?? (_meses.isEmpty ? null : _meses.last.mes);

  @override
  Widget build(BuildContext context) {
    final r = _rel;

    return Scaffold(
      appBar: AppBar(title: const Text('Relatórios')),
      body: RefreshIndicator(
        onRefresh: _recarregar,
        child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 14, 16, 32),
          children: [
            if (_erro != null) ...[
              Faixa(_erro!, aoTocar: _buscar, icone: Icons.wifi_off),
              const SizedBox(height: 14),
            ],

            Text(
              r?.periodoLabel ?? 'Carregando...',
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w600, height: 1.15),
            ),
            const SizedBox(height: 16),

            if (_carregando && r == null)
              const Column(
                children: [
                  Esqueleto(altura: 92),
                  SizedBox(height: 10),
                  Esqueleto(altura: 78),
                  SizedBox(height: 10),
                  Esqueleto(altura: 140),
                ],
              )
            else if (r != null) ...[
              if (!r.temHistorico)
                const Vazio(
                  titulo: 'Nenhuma OS concluída ainda.',
                  dica: 'Os relatórios começam a contar quando o primeiro carro é entregue.',
                  icone: Icons.insights_outlined,
                )
              else ...[
                CartaoNumero(
                  rotulo: 'Faturado',
                  valor: reais(r.faturadoCentavos),
                  detalhe: '${r.osConcluidas} ${r.osConcluidas == 1 ? "OS entregue" : "OS entregues"} no período',
                  heroi: true,
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: CartaoNumero(
                        rotulo: 'Entrou no período',
                        valor: reais(r.recebidoCentavos),
                        detalhe: 'de qualquer OS',
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: CartaoNumero(
                        rotulo: 'Ticket médio',
                        valor: reais(r.ticketMedioCentavos),
                        detalhe: 'por OS entregue',
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 18),

                Bloco(
                  titulo: 'Do que foi faturado',
                  filhos: [
                    // Verde só quando há o que comemorar: R$ 0,00 pintado de verde num mês parado
                    // dá a notícia errada de relance, que é como esta linha é lida.
                    Linha(
                      'Já recebido',
                      reais(r.faturadoRecebidoCentavos),
                      cor: r.faturadoRecebidoCentavos > 0 ? Cores.ok : null,
                    ),
                    Linha(
                      'Ainda a receber',
                      reais(r.faturadoAReceberCentavos),
                      cor: r.faturadoAReceberCentavos > 0 ? Cores.alerta : null,
                    ),
                    const SizedBox(height: 6),
                    Linha('Total faturado', reais(r.faturadoCentavos), forte: true),
                  ],
                ),
                const SizedBox(height: 12),

                Bloco(
                  titulo: 'O resto da conta',
                  filhos: [
                    Linha('Descontos dados', reais(r.descontoCentavos)),
                    Linha(
                      'Estornos',
                      reais(r.estornosCentavos),
                      cor: r.estornosCentavos > 0 ? Cores.perigo : null,
                    ),
                    Linha('Cancelamentos', '${r.cancelamentos}'),
                    Linha('Não compareceram', '${r.naoComparecimentos}'),
                  ],
                ),
                const SizedBox(height: 22),

                if (r.porForma.isNotEmpty) ...[
                  const Rotulo('Como o dinheiro entrou'),
                  const SizedBox(height: 10),
                  Bloco(
                    titulo: 'Recebido no período',
                    filhos: [
                      for (final f in r.porForma) Linha(f.formaLabel, reais(f.totalCentavos)),
                      const SizedBox(height: 6),
                      Linha('Total', reais(r.recebidoCentavos), forte: true),
                    ],
                  ),
                  const SizedBox(height: 22),
                ],

                const Rotulo('O que mais rendeu'),
                const SizedBox(height: 10),
                if (r.porServico.isEmpty)
                  const Vazio(
                    titulo: 'Nenhum serviço entregue neste mês.',
                    icone: Icons.style_outlined,
                  )
                else
                  _Ranking(servicos: r.porServico),
                const SizedBox(height: 26),
              ],
            ],

            if (_meses.length > 1) ...[
              const Rotulo('Evolução'),
              const SizedBox(height: 4),
              const Text(
                'Faturado por mês. Toque para ver o mês.',
                style: TextStyle(fontSize: 12.5, color: Cores.textoFraco),
              ),
              const SizedBox(height: 12),
              _Evolucao(meses: _meses, ativo: _mesAtivo, aoEscolher: _escolher),
            ],
          ],
        ),
      ),
    );
  }
}

/// Os serviços do período, do que mais rendeu para o que menos rendeu, com uma barra proporcional.
///
/// A barra é relativa ao PRIMEIRO colocado, não ao total: o que se lê aqui é "o segundo rende
/// metade do primeiro", e essa comparação some quando tudo é fatia de um bolo de 100%.
class _Ranking extends StatelessWidget {
  const _Ranking({required this.servicos});

  final List<ServicoDoRelatorio> servicos;

  @override
  Widget build(BuildContext context) {
    final lista = [...servicos]..sort((a, b) => b.totalCentavos.compareTo(a.totalCentavos));
    final topo = lista.take(8).toList();
    final maior = topo.isEmpty ? 0 : topo.first.totalCentavos;

    return Column(
      children: [
        for (final s in topo) ...[
          Container(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            decoration: BoxDecoration(
              color: Cores.superficie,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Cores.linha),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        s.nome,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      reais(s.totalCentavos),
                      style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                ClipRRect(
                  borderRadius: BorderRadius.circular(3),
                  child: LinearProgressIndicator(
                    value: maior == 0 ? 0 : s.totalCentavos / maior,
                    minHeight: 6,
                    backgroundColor: Cores.linha.withValues(alpha: 0.6),
                    valueColor: const AlwaysStoppedAnimation(Cores.ouro),
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  s.quantidade == 1 ? '1 vez' : '${s.quantidade} vezes',
                  style: const TextStyle(fontSize: 12, color: Cores.textoFraco),
                ),
              ],
            ),
          ),
          const SizedBox(height: 10),
        ],
        if (lista.length > topo.length)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(
              'e mais ${lista.length - topo.length} ${lista.length - topo.length == 1 ? "serviço" : "serviços"} — a lista inteira está no painel.',
              style: const TextStyle(fontSize: 12, color: Cores.textoFraco),
            ),
          ),
      ],
    );
  }
}

/// Doze barras e nada mais: sem eixo, sem grade, sem número em cima de cada uma.
///
/// Num celular, o gráfico serve para responder "está subindo ou descendo" em meio segundo. O valor
/// exato de cada mês tem lugar próprio — é tocar na barra e ler o relatório inteiro em cima.
/// Altura da área de barras. A barra cresce até ela; o alvo de toque ocupa ela inteira.
const _alturaDoGrafico = 79.0;

class _Evolucao extends StatelessWidget {
  const _Evolucao({required this.meses, required this.ativo, required this.aoEscolher});

  final List<MesDoRelatorio> meses;
  final String? ativo;
  final void Function(MesDoRelatorio) aoEscolher;

  @override
  Widget build(BuildContext context) {
    final maior = meses.fold<int>(0, (m, x) => x.faturadoCentavos > m ? x.faturadoCentavos : m);

    return Container(
      padding: const EdgeInsets.fromLTRB(10, 14, 10, 8),
      decoration: BoxDecoration(
        color: Cores.superficie,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Cores.linha),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          for (final m in meses)
            Expanded(
              child: _Barra(
                mes: m,
                // Mês sem faturamento mostra um toco de 3px em vez de nada: barra invisível parece
                // mês que não existe, e o toque para abri-lo some junto.
                altura: maior == 0 ? 3 : 3 + (m.faturadoCentavos / maior) * (_alturaDoGrafico - 3),
                ativo: m.mes == ativo,
                aoTocar: () => aoEscolher(m),
              ),
            ),
        ],
      ),
    );
  }
}

class _Barra extends StatelessWidget {
  const _Barra({required this.mes, required this.altura, required this.ativo, required this.aoTocar});

  final MesDoRelatorio mes;
  final double altura;
  final bool ativo;
  final VoidCallback aoTocar;

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: aoTocar,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 2, vertical: 4),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Altura FIXA com a barra encostada embaixo. Se a coluna tivesse o tamanho da barra,
              // o alvo de toque encolheria junto — e mês parado, que é o que vira barra de 3px, é
              // exatamente o mês que se quer abrir para entender o que aconteceu.
              SizedBox(
                height: _alturaDoGrafico,
                child: Align(
                  alignment: Alignment.bottomCenter,
                  child: Container(
                    height: altura,
                    width: double.infinity,
                    decoration: BoxDecoration(
                      color: ativo ? Cores.ouro : Cores.ouro.withValues(alpha: 0.28),
                      borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 6),
              Text(
                // "Set/26" não cabe em 1/12 da tela; o mês sozinho cabe e basta para orientar.
                mes.labelCurto.split('/').first,
                maxLines: 1,
                style: TextStyle(
                  fontSize: 10,
                  height: 1.1,
                  fontWeight: ativo ? FontWeight.w700 : FontWeight.w400,
                  color: ativo ? Cores.texto : Cores.textoFraco,
                ),
              ),
            ],
          ),
        ),
      );
}
