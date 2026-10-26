import 'package:flutter/material.dart';

import '../api.dart';
import '../tema.dart';

class TelaLogin extends StatefulWidget {
  const TelaLogin({required this.api, required this.aoEntrar, super.key});
  final Api api;
  final VoidCallback aoEntrar;

  @override
  State<TelaLogin> createState() => _TelaLoginState();
}

class _TelaLoginState extends State<TelaLogin> {
  final _email = TextEditingController();
  final _senha = TextEditingController();
  bool _enviando = false;
  String? _erro;

  @override
  void dispose() {
    _email.dispose();
    _senha.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    // o "Go" do teclado não olhava o botão: duas teclas viravam dois logins e duas sessões
    if (_enviando) return;
    setState(() {
      _enviando = true;
      _erro = null;
    });
    try {
      await widget.api.entrar(_email.text.trim(), _senha.text);
      widget.aoEntrar();
      return; // a tela já foi trocada: mexer no State daqui para baixo é mexer em widget morto
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
                  'KADOSH',
                  style: TextStyle(
                    color: Cores.marfim,
                    fontSize: 30,
                    letterSpacing: 10,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 6),
                const Text(
                  'DETAIL',
                  style: TextStyle(color: Cores.ouro, fontSize: 12, letterSpacing: 8),
                ),
                const SizedBox(height: 44),
                TextField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  autocorrect: false,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(labelText: 'E-mail'),
                ),
                const SizedBox(height: 14),
                TextField(
                  controller: _senha,
                  obscureText: true,
                  textInputAction: TextInputAction.go,
                  onSubmitted: (_) => _entrar(),
                  decoration: const InputDecoration(labelText: 'Senha'),
                ),
                if (_erro != null) ...[
                  const SizedBox(height: 16),
                  Text(_erro!, style: const TextStyle(color: Color(0xFFE79A93), fontSize: 14.5)),
                ],
                const SizedBox(height: 24),
                FilledButton(
                  onPressed: _enviando ? null : _entrar,
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
                      : const Text('Entrar'),
                ),
                const SizedBox(height: 18),
                // O endereço do servidor em letra pequena: para o sócio é ruído, mas é a única
                // pista em campo quando o APK sai sem `--dart-define` e nada conecta.
                Text(
                  'Servidor: ${Api.base}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Cores.textoFraco, fontSize: 11.5),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
