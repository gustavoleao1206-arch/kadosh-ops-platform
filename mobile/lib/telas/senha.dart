import 'package:flutter/material.dart';

import '../api.dart';
import '../tema.dart';

/// Troca da senha temporária.
///
/// Usuário criado pelo CLI ou senha resetada no painel vem com `must_change_password`: o backend
/// responde 403 em tudo até a troca. Sem esta tela, o sócio entrava, via o pátio abrir e levava
/// "Troque sua senha antes de continuar." para sempre, sem lugar nenhum onde trocar.
class TelaTrocarSenha extends StatefulWidget {
  const TelaTrocarSenha({
    required this.api,
    required this.aoTrocar,
    required this.aoSair,
    super.key,
  });

  final Api api;
  final VoidCallback aoTrocar;
  final Future<void> Function() aoSair;

  @override
  State<TelaTrocarSenha> createState() => _TelaTrocarSenhaState();
}

class _TelaTrocarSenhaState extends State<TelaTrocarSenha> {
  static const _minimo = 10; // igual ao MIN_PASSWORD_LENGTH do backend

  final _atual = TextEditingController();
  final _nova = TextEditingController();
  final _confirma = TextEditingController();
  bool _enviando = false;
  String? _erro;

  @override
  void dispose() {
    _atual.dispose();
    _nova.dispose();
    _confirma.dispose();
    super.dispose();
  }

  bool get _pode =>
      _atual.text.isNotEmpty &&
      _nova.text.length >= _minimo &&
      _nova.text == _confirma.text &&
      _nova.text != _atual.text;

  Future<void> _trocar() async {
    setState(() {
      _enviando = true;
      _erro = null;
    });
    try {
      await widget.api.trocarSenha(_atual.text, _nova.text);
      widget.aoTrocar();
    } on ErroApi catch (e) {
      if (mounted) setState(() => _erro = e.mensagem);
    } catch (_) {
      if (mounted) setState(() => _erro = 'Sem conexão com o servidor.');
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Cores.obsidiana,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Crie sua senha',
                  style: TextStyle(color: Cores.marfim, fontSize: 24, fontWeight: FontWeight.w600),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Sua senha atual é temporária. Escolha uma nova para continuar.',
                  style: TextStyle(color: Color(0xFF9C978C), fontSize: 14.5, height: 1.35),
                ),
                const SizedBox(height: 28),
                TextField(
                  controller: _atual,
                  obscureText: true,
                  onChanged: (_) => setState(() {}),
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(labelText: 'Senha temporária'),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _nova,
                  obscureText: true,
                  onChanged: (_) => setState(() {}),
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: 'Nova senha',
                    helperText: 'Mínimo de $_minimo caracteres',
                  ),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _confirma,
                  obscureText: true,
                  onChanged: (_) => setState(() {}),
                  textInputAction: TextInputAction.go,
                  onSubmitted: (_) => _pode && !_enviando ? _trocar() : null,
                  decoration: const InputDecoration(labelText: 'Repita a nova senha'),
                ),
                if (_confirma.text.isNotEmpty && _nova.text != _confirma.text) ...[
                  const SizedBox(height: 10),
                  const Text(
                    'As duas não são iguais.',
                    style: TextStyle(color: Color(0xFFE79A93), fontSize: 14),
                  ),
                ],
                if (_erro != null) ...[
                  const SizedBox(height: 16),
                  Text(_erro!, style: const TextStyle(color: Color(0xFFE79A93), fontSize: 14.5)),
                ],
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _pode && !_enviando ? _trocar : null,
                  style: FilledButton.styleFrom(
                    backgroundColor: Cores.ouro,
                    foregroundColor: Cores.obsidiana,
                  ),
                  child: _enviando
                      ? const SizedBox(
                          height: 22,
                          width: 22,
                          child: CircularProgressIndicator(strokeWidth: 2.4, color: Cores.obsidiana),
                        )
                      : const Text('Salvar e entrar'),
                ),
                const SizedBox(height: 10),
                TextButton(
                  onPressed: _enviando ? null : () => widget.aoSair(),
                  child: const Text('Sair', style: TextStyle(color: Cores.textoFraco)),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
