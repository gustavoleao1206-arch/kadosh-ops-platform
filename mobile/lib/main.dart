import 'package:flutter/material.dart';

import 'api.dart';
import 'tema.dart';
import 'telas/login.dart';
import 'telas/inicio.dart';
import 'telas/senha.dart';

void main() => runApp(const KadoshCampo());

class KadoshCampo extends StatefulWidget {
  const KadoshCampo({super.key});

  @override
  State<KadoshCampo> createState() => _KadoshCampoState();
}

class _KadoshCampoState extends State<KadoshCampo> {
  final api = Api();
  final _navegador = GlobalKey<NavigatorState>();
  bool _carregando = true;

  @override
  void initState() {
    super.initState();
    api.aoExpirar = _sessaoCaiu;
    _abrir();
  }

  /// O app abre já logado: o sócio não digita senha dez vezes por dia. O token fica guardado e a
  /// sessão só cai quando o servidor a recusa (401) ou ele sai de propósito.
  Future<void> _abrir() async {
    await api.carregarToken();
    if (api.autenticado) {
      try {
        await api.eu();
      } on ErroApi catch (e) {
        // Só o 401 mata a sessão. Um 500 ou um 502 de cold start é o servidor tossindo — o token
        // continua valendo, e mandar o sócio digitar a senha no meio do pátio por causa disso é
        // exatamente o que esta tela existe para evitar.
        if (e.status == 401) await api.sair();
      } catch (_) {
        // Sem rede na abertura: entra assim mesmo, com a sessão guardada, e deixa a tela do pátio
        // pedir para puxar de novo. Deixar a exceção escapar daqui congelava o app na rodinha.
      }
    }
    if (mounted) setState(() => _carregando = false);
  }

  /// Servidor recusou a sessão em qualquer tela. Volta para a raiz antes de trocar o conteúdo:
  /// sem isso, a tela da OS continuaria empilhada por cima do login.
  void _sessaoCaiu() {
    if (!mounted) return;
    _navegador.currentState?.popUntil((r) => r.isFirst);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Kadosh Campo',
      debugShowCheckedModeBanner: false,
      navigatorKey: _navegador,
      theme: montarTema(),
      home: _carregando
          ? const Scaffold(body: Center(child: CircularProgressIndicator()))
          : _porta(),
    );
  }

  Widget _porta() {
    if (!api.autenticado) return TelaLogin(api: api, aoEntrar: () => setState(() {}));
    // Senha temporária (usuário criado pelo CLI ou senha resetada no painel): o backend responde
    // 403 em tudo até ela ser trocada. Abrir o pátio aqui daria uma faixa vermelha eterna.
    if (api.precisaTrocarSenha) {
      return TelaTrocarSenha(api: api, aoTrocar: () => setState(() {}), aoSair: _deslogar);
    }
    return TelaInicio(api: api, aoSair: _deslogar);
  }

  Future<void> _deslogar() async {
    await api.sair();
    if (mounted) setState(() {});
  }
}
