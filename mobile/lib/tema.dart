import 'package:flutter/material.dart';

/// Paleta da marca. No celular o tema é CLARO e de alto contraste: a tela é lida sob sol, no meio
/// do pátio. O ouro entra só como acento (decisão 8 da arquitetura), nunca como fundo de área
/// grande — em tela clara ele vira mancha e come a legibilidade.
class Cores {
  static const obsidiana = Color(0xFF0B0B0D);
  static const carbono = Color(0xFF1C1C22);
  static const ouro = Color(0xFFB8902F);
  static const marfim = Color(0xFFECE6D8);

  static const fundo = Color(0xFFF7F6F3);
  static const superficie = Colors.white;
  static const linha = Color(0xFFE2DFD8);
  static const texto = Color(0xFF16161A);
  static const textoFraco = Color(0xFF6B6862);

  static const ok = Color(0xFF2E7D52);
  static const alerta = Color(0xFFB2610F);
  static const perigo = Color(0xFFB3261E);

  /// Traduz o `tone` que vem da API. O app não decide cor de status — só sabe pintar o que recebe.
  static Color doTone(String tone) => switch (tone) {
        'ok' => ok,
        'warn' => alerta,
        'danger' => perigo,
        'gold' => ouro,
        _ => textoFraco,
      };
}

/// Alvos de toque grandes de propósito: a mão está molhada e o celular na horizontal do peito.
/// 56 dp é o mínimo confortável — o padrão do Material (48) erra demais nessa situação.
const alturaBotao = 56.0;

ThemeData montarTema() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: Cores.ouro,
      primary: Cores.obsidiana,
      surface: Cores.superficie,
      brightness: Brightness.light,
    ),
    scaffoldBackgroundColor: Cores.fundo,
  );

  return base.copyWith(
    appBarTheme: const AppBarTheme(
      backgroundColor: Cores.obsidiana,
      foregroundColor: Cores.marfim,
      elevation: 0,
      centerTitle: false,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size.fromHeight(alturaBotao),
        backgroundColor: Cores.obsidiana,
        foregroundColor: Cores.marfim,
        textStyle: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size.fromHeight(alturaBotao),
        foregroundColor: Cores.texto,
        side: const BorderSide(color: Cores.linha),
        textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w500),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Cores.superficie,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: Cores.linha),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(8),
        borderSide: const BorderSide(color: Cores.linha),
      ),
    ),
    cardTheme: CardThemeData(
      color: Cores.superficie,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: const BorderSide(color: Cores.linha),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
  );
}

/// Etiqueta de status, com a cor que a API mandou.
class Etiqueta extends StatelessWidget {
  const Etiqueta(this.texto, {required this.tone, super.key});
  final String texto;
  final String tone;

  @override
  Widget build(BuildContext context) {
    final cor = Cores.doTone(tone);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: cor.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(5),
        border: Border.all(color: cor.withValues(alpha: 0.35)),
      ),
      child: Text(
        texto.toUpperCase(),
        style: TextStyle(color: cor, fontSize: 11.5, fontWeight: FontWeight.w700, letterSpacing: 0.6),
      ),
    );
  }
}
