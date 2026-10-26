/// Peças visuais compartilhadas.
///
/// Existem porque `_Bloco`, `_Faixa` e `_Linha` estavam copiados em os.dart, caixa.dart e
/// patio.dart — três cópias que já divergiam em espaçamento. Kit ANTES de tela nova: começar pelas
/// telas e "extrair depois" é como as três cópias nasceram.
///
/// Regra de cor da casa, valendo aqui: o ouro é marca e acento, nunca dinheiro nem fundo de área
/// grande. Valor monetário sai em `Cores.texto`; quem fala de estado é a tríade ok/alerta/perigo.
library;

import 'package:flutter/material.dart';

import 'modelos.dart';
import 'tema.dart';

/// Cartão com título em caixa-alta espaçada — a assinatura tipográfica da marca.
class Bloco extends StatelessWidget {
  const Bloco({required this.titulo, required this.filhos, this.acao, super.key});

  final String titulo;
  final List<Widget> filhos;
  final Widget? acao;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
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
              Expanded(child: Rotulo(titulo)),
              ?acao,
            ],
          ),
          const SizedBox(height: 12),
          ...filhos,
        ],
      ),
    );
  }
}

class Rotulo extends StatelessWidget {
  const Rotulo(this.texto, {super.key});
  final String texto;

  @override
  Widget build(BuildContext context) => Text(
        texto.toUpperCase(),
        style: const TextStyle(
          fontSize: 11.5,
          fontWeight: FontWeight.w700,
          letterSpacing: 1.6,
          color: Cores.textoFraco,
        ),
      );
}

/// Faixa de aviso. `tone` vem da API quando existir; o app não escolhe cor por conta própria.
class Faixa extends StatelessWidget {
  const Faixa(this.texto, {this.tone = 'danger', this.aoTocar, this.icone, super.key});

  final String texto;
  final String tone;
  final VoidCallback? aoTocar;
  final IconData? icone;

  @override
  Widget build(BuildContext context) {
    final cor = Cores.doTone(tone);
    final corpo = Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: cor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: cor.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          Icon(icone ?? Icons.error_outline, size: 18, color: cor),
          const SizedBox(width: 10),
          Expanded(
            child: Text(texto, style: TextStyle(color: cor, fontSize: 13.5, height: 1.35)),
          ),
          if (aoTocar != null) Icon(Icons.chevron_right, size: 18, color: cor),
        ],
      ),
    );
    if (aoTocar == null) return corpo;
    return InkWell(borderRadius: BorderRadius.circular(8), onTap: aoTocar, child: corpo);
  }
}

/// Linha rótulo → valor. `forte` marca o número que importa naquele bloco.
class Linha extends StatelessWidget {
  const Linha(this.rotulo, this.valor, {this.forte = false, this.cor, super.key});

  final String rotulo;
  final String valor;
  final bool forte;
  final Color? cor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(rotulo, style: const TextStyle(color: Cores.textoFraco, fontSize: 14)),
          Text(
            valor,
            style: TextStyle(
              fontSize: forte ? 16 : 14,
              fontWeight: forte ? FontWeight.w700 : FontWeight.w500,
              color: cor ?? Cores.texto,
              // dígitos de largura fixa: sem isso a coluna de valores dança a cada centavo
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ],
      ),
    );
  }
}

/// Cartão de indicador. Um `heroi` por tela — o resto é secundário e menor.
class CartaoNumero extends StatelessWidget {
  const CartaoNumero({
    required this.rotulo,
    required this.valor,
    this.detalhe,
    this.tone,
    this.heroi = false,
    this.aoTocar,
    super.key,
  });

  final String rotulo;
  final String valor;
  final String? detalhe;
  final String? tone;
  final bool heroi;
  final VoidCallback? aoTocar;

  @override
  Widget build(BuildContext context) {
    final cor = tone == null ? Cores.texto : Cores.doTone(tone!);
    final corpo = Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Cores.superficie,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: tone == null ? Cores.linha : Cores.doTone(tone!).withValues(alpha: 0.35),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Rotulo(rotulo),
          const SizedBox(height: 8),
          Text(
            valor,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: heroi ? 30 : 22,
              fontWeight: FontWeight.w700,
              height: 1.05,
              color: cor,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
          if (detalhe != null) ...[
            const SizedBox(height: 6),
            Text(
              detalhe!,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 12.5, color: Cores.textoFraco, height: 1.25),
            ),
          ],
        ],
      ),
    );
    if (aoTocar == null) return corpo;
    return InkWell(borderRadius: BorderRadius.circular(10), onTap: aoTocar, child: corpo);
  }
}

/// Botão grande de navegação da tela inicial. 56 dp de altura mínima, pela mesma razão do resto do
/// app: mão molhada, celular na horizontal do peito.
class BotaoGrande extends StatelessWidget {
  const BotaoGrande({
    required this.icone,
    required this.titulo,
    required this.aoTocar,
    this.detalhe,
    this.destaque = false,
    super.key,
  });

  final IconData icone;
  final String titulo;
  final String? detalhe;
  final VoidCallback aoTocar;
  final bool destaque;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: destaque ? Cores.obsidiana : Cores.superficie,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: aoTocar,
        child: Container(
          constraints: const BoxConstraints(minHeight: alturaBotao),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: destaque ? Cores.obsidiana : Cores.linha),
          ),
          child: Row(
            children: [
              Icon(icone, size: 22, color: destaque ? Cores.ouro : Cores.ouro),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      titulo,
                      style: TextStyle(
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                        color: destaque ? Cores.marfim : Cores.texto,
                      ),
                    ),
                    if (detalhe != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          detalhe!,
                          style: TextStyle(
                            fontSize: 12.5,
                            color: destaque ? Cores.marfim.withValues(alpha: 0.7) : Cores.textoFraco,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              Icon(
                Icons.chevron_right,
                color: destaque ? Cores.marfim.withValues(alpha: 0.6) : Cores.textoFraco,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Esqueleto de carregamento. Mantém a forma da tela enquanto os dados vêm, em vez de apagar tudo
/// com um spinner e fazer o layout pular quando chegam.
class Esqueleto extends StatelessWidget {
  const Esqueleto({this.altura = 16, this.largura, super.key});
  final double altura;
  final double? largura;

  @override
  Widget build(BuildContext context) => Container(
        height: altura,
        width: largura,
        decoration: BoxDecoration(
          color: Cores.linha.withValues(alpha: 0.55),
          borderRadius: BorderRadius.circular(6),
        ),
      );
}

/// Estado vazio com a próxima ação — nunca só "nada aqui".
class Vazio extends StatelessWidget {
  const Vazio({required this.titulo, this.dica, this.icone, super.key});
  final String titulo;
  final String? dica;
  final IconData? icone;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 12),
        child: Column(
          children: [
            Icon(icone ?? Icons.inbox_outlined, size: 28, color: Cores.linha),
            const SizedBox(height: 10),
            Text(
              titulo,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
            ),
            if (dica != null) ...[
              const SizedBox(height: 6),
              Text(
                dica!,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 13, color: Cores.textoFraco, height: 1.35),
              ),
            ],
          ],
        ),
      );
}

/// Etiqueta da régua de cobrança, com o rótulo e a cor que a API mandou.
class EtiquetaCobranca extends StatelessWidget {
  const EtiquetaCobranca(this.os, {super.key});
  final OS os;

  @override
  Widget build(BuildContext context) {
    final label = os.situacaoCobrancaLabel;
    if (label == null) return const SizedBox.shrink();
    return Etiqueta(label, tone: os.situacaoCobrancaTone ?? 'neutral');
  }
}
