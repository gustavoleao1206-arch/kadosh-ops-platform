import 'package:flutter/material.dart';

import '../api.dart';
import '../financeiro.dart';
import '../modelos.dart';
import '../tema.dart';
import '../ui.dart';
import 'agenda.dart';
import 'caixa.dart';
import 'catalogo.dart';
import 'clientes.dart';
import 'financeiro.dart';
import 'patio.dart';
import 'receber.dart';
import 'relatorios.dart';

/// A primeira tela do app: o dia, o mês, quem deve — e os quatro botões que levam ao trabalho.
///
/// Antes desta fase a home era o pátio direto. Funcionava para quem chega e começa a mexer em
/// carro, mas escondia o financeiro num ícone da barra e não dizia nada sobre cobrança atrasada.
/// Agora o pátio é um toque de distância, e o que mudou é que o número do dia e a dívida em aberto
/// aparecem antes.
///
/// UMA chamada (`/dashboard`) monta a tela inteira. O balcão abre isto muitas vezes por dia, no
/// celular, muitas vezes com sinal ruim: uma requisição, um esqueleto, um desenho.
class TelaInicio extends StatefulWidget {
  const TelaInicio({required this.api, required this.aoSair, super.key});

  final Api api;
  final Future<void> Function() aoSair;

  @override
  State<TelaInicio> createState() => _TelaInicioState();
}

class _TelaInicioState extends State<TelaInicio> {
  Resumo? _resumo;
  String? _erro;
  bool _carregando = true;

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
      final j = await widget.api.get('/dashboard');
      if (!mounted) return;
      setState(() {
        _resumo = Resumo.doJson(j as Map<String, dynamic>);
        _carregando = false;
      });
    } catch (e) {
      if (!mounted) return;
      // catch genérico de propósito: sem rede, o `get` estoura antes de virar ErroApi, e a tela
      // não pode ficar num spinner eterno.
      setState(() {
        _erro = mensagemDeErro(e);
        _carregando = false;
      });
    }
  }

  Future<void> _abrir(Widget tela) async {
    await Navigator.of(context).push(MaterialPageRoute<bool>(builder: (_) => tela));
    // qualquer coisa feita lá dentro pode ter mexido em dinheiro: ao voltar, os números refazem
    if (mounted) await _buscar();
  }

  String get _saudacao {
    final h = DateTime.now().hour;
    if (h < 12) return 'Bom dia';
    if (h < 18) return 'Boa tarde';
    return 'Boa noite';
  }

  @override
  Widget build(BuildContext context) {
    final r = _resumo;
    return Scaffold(
      appBar: AppBar(
        title: const Text('KADOSH', style: TextStyle(letterSpacing: 4, fontWeight: FontWeight.w300)),
        actions: [
          IconButton(
            tooltip: 'Sair',
            onPressed: _confirmarSaida,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _buscar,
        child: ListView(
          // sem isto o gesto de puxar não é aceito quando o conteúdo cabe na tela — que é
          // justamente o estado de erro, onde a tela manda puxar
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
          children: [
            Text(
              '$_saudacao.',
              style: const TextStyle(fontSize: 26, fontWeight: FontWeight.w600, height: 1.1),
            ),
            const SizedBox(height: 4),
            const Text(
              'O dia, o mês e quem ainda deve.',
              style: TextStyle(fontSize: 14, color: Cores.textoFraco),
            ),
            const SizedBox(height: 18),

            if (_erro != null) ...[
              Faixa(_erro!, aoTocar: _buscar, icone: Icons.wifi_off),
              const SizedBox(height: 16),
            ],

            // Cobrança atrasada vem ANTES de tudo: carro entregue sem receber é a informação mais
            // acionável do dia, e no celular ela some se ficar abaixo da dobra.
            if (r != null && r.cobranca.atrasados.qtd > 0) ...[
              Faixa(
                '${r.cobranca.atrasados.qtd == 1 ? "1 cobrança atrasada" : "${r.cobranca.atrasados.qtd} cobranças atrasadas"} · '
                '${reais(r.cobranca.atrasados.totalCentavos)} entregues e não recebidos.',
                icone: Icons.warning_amber_rounded,
                aoTocar: () => _abrir(
                  TelaFinanceiro(api: widget.api, abaInicial: AbaFinanceiro.cobrancas, situacaoInicial: 'atrasado'),
                ),
              ),
              const SizedBox(height: 16),
            ],

            if (_carregando && r == null)
              const _EsqueletoInicio()
            else if (r != null) ...[
              CartaoNumero(
                rotulo: 'Recebido hoje',
                valor: reais(r.hoje.recebidoCentavos),
                detalhe: 'Entrou no caixa de hoje',
                heroi: true,
                aoTocar: () => _abrir(TelaCaixa(api: widget.api)),
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: CartaoNumero(
                      rotulo: 'A receber',
                      valor: reais(r.cobranca.pendentes.totalCentavos),
                      detalhe: '${r.cobranca.pendentes.qtd} em aberto',
                      tone: r.cobranca.pendentes.qtd > 0 ? 'warn' : null,
                      aoTocar: () => _abrir(
                        TelaFinanceiro(
                          api: widget.api,
                          abaInicial: AbaFinanceiro.cobrancas,
                          situacaoInicial: 'pendente',
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: CartaoNumero(
                      rotulo: r.mes.label,
                      valor: reais(r.mes.faturadoCentavos),
                      detalhe: '${r.mes.osConcluidas} ${r.mes.osConcluidas == 1 ? "OS entregue" : "OS entregues"}',
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 22),
            ],

            const Rotulo('O que fazer'),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.local_car_wash_outlined,
              titulo: 'Pátio',
              detalhe: r == null ? null : '${r.hoje.noPatioQtd} na loja agora',
              destaque: true,
              aoTocar: () => _abrir(TelaPatio(api: widget.api, aoSair: widget.aoSair, comoRaiz: false)),
            ),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.add_circle_outline,
              titulo: 'Receber veículo',
              detalhe: r == null ? null : '${r.hoje.chegamQtd} chegam hoje',
              aoTocar: () => _abrir(TelaReceber(api: widget.api)),
            ),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.point_of_sale_outlined,
              titulo: 'Caixa de hoje',
              aoTocar: () => _abrir(TelaCaixa(api: widget.api)),
            ),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.receipt_long_outlined,
              titulo: 'Financeiro',
              detalhe: 'Extrato e cobranças',
              aoTocar: () => _abrir(TelaFinanceiro(api: widget.api)),
            ),
            const SizedBox(height: 26),

            // Duas seções, e a divisão não é de gosto: em cima o que MUDA a loja (mexe em carro,
            // em OS, em dinheiro); aqui embaixo o que só RESPONDE pergunta. Quem está com a mão
            // ocupada procura na primeira lista; quem está no telefone com o cliente, na segunda.
            const Rotulo('Consultar'),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.event_note_outlined,
              titulo: 'Agenda',
              detalhe: r == null ? null : '${r.hoje.chegamQtd} marcados para hoje',
              aoTocar: () => _abrir(TelaAgenda(api: widget.api)),
            ),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.people_outline,
              titulo: 'Clientes',
              detalhe: 'Telefone e histórico',
              aoTocar: () => _abrir(TelaClientes(api: widget.api)),
            ),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.style_outlined,
              titulo: 'Catálogo',
              detalhe: 'Tabela de preços',
              aoTocar: () => _abrir(TelaCatalogo(api: widget.api)),
            ),
            const SizedBox(height: 10),
            BotaoGrande(
              icone: Icons.insights_outlined,
              titulo: 'Relatórios',
              detalhe: 'O mês fechado, mês a mês',
              aoTocar: () => _abrir(TelaRelatorios(api: widget.api)),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmarSaida() async {
    final sair = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Sair do aplicativo?'),
        content: const Text('Você precisará entrar de novo com e-mail e senha.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Ficar')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Sair')),
        ],
      ),
    );
    if (sair == true) await widget.aoSair();
  }
}

class _EsqueletoInicio extends StatelessWidget {
  const _EsqueletoInicio();

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Cores.superficie,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Cores.linha),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Esqueleto(altura: 11, largura: 90),
                SizedBox(height: 10),
                Esqueleto(altura: 28, largura: 160),
                SizedBox(height: 8),
                Esqueleto(altura: 11, largura: 120),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: List.generate(
              2,
              (i) => Expanded(
                child: Padding(
                  padding: EdgeInsets.only(right: i == 0 ? 10 : 0),
                  child: Container(
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: Cores.superficie,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: Cores.linha),
                    ),
                    child: const Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Esqueleto(altura: 11, largura: 70),
                        SizedBox(height: 10),
                        Esqueleto(altura: 20, largura: 100),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 22),
        ],
      );
}
