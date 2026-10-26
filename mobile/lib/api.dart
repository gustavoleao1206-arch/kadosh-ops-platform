import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Cliente da API do Kadosh Ops.
///
/// Duas diferenças em relação ao painel, e só duas: a sessão viaja como Bearer (o painel usa
/// cookie HttpOnly) e o endereço do servidor entra em tempo de build. Todo o resto — regras,
/// rótulos, cores, o que dá para fazer com cada OS — continua vindo do backend.
class Api {
  /// Trocado no build: `flutter build apk --dart-define=KADOSH_API=https://...`.
  /// O padrão aponta para o host da máquina visto de dentro do emulador Android.
  static const base = String.fromEnvironment('KADOSH_API', defaultValue: 'http://10.0.2.2:8000');

  /// Sinal fantasma (barra cheia, sem trânsito) é o normal dentro de um box de lavagem. Sem teto,
  /// o socket fica pendurado e o botão vira um spinner que nunca sai — pior que o erro.
  static const _espera = Duration(seconds: 20);

  static const _chaveToken = 'kadosh_token';

  final _http = http.Client();
  String? _token;
  bool _precisaTrocarSenha = false;

  /// Avisado quando o servidor recusa a sessão. Tratar 401 tela a tela deixa o sócio preso numa
  /// faixa vermelha sem caminho para o login — daqui ele vai para a porta de entrada, de onde
  /// quer que esteja.
  void Function()? aoExpirar;

  bool get autenticado => _token != null;

  /// Senha temporária do CLI ou reset pelo painel: o backend responde 403 em tudo até ela ser
  /// trocada. Sem olhar esta flag, o app abriria o pátio e levaria 403 para sempre.
  bool get precisaTrocarSenha => _precisaTrocarSenha;

  Future<void> carregarToken() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString(_chaveToken);
  }

  Future<void> _guardarToken(String? valor) async {
    _token = valor;
    final prefs = await SharedPreferences.getInstance();
    if (valor == null) {
      await prefs.remove(_chaveToken);
    } else {
      await prefs.setString(_chaveToken, valor);
    }
  }

  // `dynamic` no valor porque o backend aceita parâmetro repetido (`?status=a&status=b`), e
  // `Uri.replace` só monta isso a partir de um `Iterable<String>`.
  Uri _url(String caminho, [Map<String, dynamic>? query]) =>
      montarUrl(base, caminho, query);

  Map<String, String> get _cabecalhos => {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        if (_token != null) 'Authorization': 'Bearer $_token',
      };

  Future<dynamic> get(String caminho, [Map<String, dynamic>? query]) async =>
      _resposta(await _http.get(_url(caminho, query), headers: _cabecalhos).timeout(_espera));

  Future<dynamic> post(String caminho, Object corpo, {Duration? espera}) async => _resposta(
        await _http
            .post(_url(caminho), headers: _cabecalhos, body: jsonEncode(corpo))
            .timeout(espera ?? _espera),
      );

  Future<dynamic> patch(String caminho, Object corpo) async => _resposta(
        await _http
            .patch(_url(caminho), headers: _cabecalhos, body: jsonEncode(corpo))
            .timeout(_espera),
      );

  /// O status manda, e só depois o corpo é lido.
  ///
  /// Ler antes custou caro: o proxy do Render responde 502 em HTML, e um portal cativo de wi-fi
  /// também. O `jsonDecode` estourava um `FormatException` que não é `ErroApi`, a tela caía no
  /// `catch` genérico e o sócio via "sem conexão" com cinco barras de sinal — diagnóstico errado,
  /// que é pior do que nenhum. E a mensagem de servidor fora do ar nunca chegava a aparecer.
  dynamic _resposta(http.Response r) {
    final ok = r.statusCode >= 200 && r.statusCode < 300;
    dynamic corpo;
    try {
      corpo = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    } on FormatException {
      if (ok) return null;
      corpo = null; // 502 em HTML: o status já diz o que aconteceu
    }
    if (ok) return corpo;
    if (r.statusCode == 401) {
      _token = null;
      _precisaTrocarSenha = false;
      SharedPreferences.getInstance().then((p) => p.remove(_chaveToken));
      aoExpirar?.call();
    }
    throw ErroApi(r.statusCode, _mensagem(corpo, r.statusCode));
  }

  /// Mesma leitura de erro do painel: o backend manda `detail` como texto, e o Pydantic manda uma
  /// lista de problemas por campo. Sem tratar os dois, o balcão vê "Instance of ..." na tela.
  String _mensagem(dynamic corpo, int status) {
    if (corpo is Map && corpo['detail'] != null) {
      final d = corpo['detail'];
      if (d is String) return d;
      if (d is List && d.isNotEmpty) {
        final primeiro = d.first;
        if (primeiro is Map && primeiro['msg'] != null) return primeiro['msg'].toString();
      }
    }
    if (status == 401) return 'Sessão encerrada. Entre de novo.';
    if (status >= 500) return 'O servidor não respondeu. Tente de novo em instantes.';
    return 'Não deu para completar (erro $status).';
  }

  Future<Map<String, dynamic>> entrar(String email, String senha) async {
    final r = await post('/auth/login', {'email': email, 'senha': senha, 'client': 'android'});
    final mapa = r as Map<String, dynamic>;
    await _guardarToken(mapa['token'] as String?);
    final user = mapa['user'] as Map<String, dynamic>;
    _precisaTrocarSenha = (user['must_change_password'] as bool?) ?? false;
    return user;
  }

  Future<void> trocarSenha(String atual, String nova) async {
    await post('/auth/change-password', {'senha_atual': atual, 'senha_nova': nova});
    _precisaTrocarSenha = false;
  }

  Future<void> sair() async {
    try {
      // teto curto: "Sair" tem de responder ao toque mesmo com o servidor mudo
      await post('/auth/logout', const {}, espera: const Duration(seconds: 5));
    } catch (_) {
      // sair é local: se o servidor não responder, o token some do aparelho do mesmo jeito
    }
    _precisaTrocarSenha = false;
    await _guardarToken(null);
  }

  Future<Map<String, dynamic>> eu() async {
    final user = (await get('/auth/me')) as Map<String, dynamic>;
    _precisaTrocarSenha = (user['must_change_password'] as bool?) ?? false;
    return user;
  }
}

class ErroApi implements Exception {
  ErroApi(this.status, this.mensagem);
  final int status;
  final String mensagem;

  /// 409 e 400 numa transição costumam significar "isso já aconteceu" — o toque anterior chegou.
  bool get talvezJaFeito => status == 409 || status == 400;

  @override
  String toString() => mensagem;
}


/// A mensagem que a tela mostra para qualquer falha de requisição.
///
/// O 401 já foi tratado pelo próprio [Api] (volta para o login), então aqui só resta o que dá para
/// escrever na tela. O `catch` genérico existe porque sem rede o erro nem chega a virar [ErroApi]:
/// estoura antes, e a tela ficaria num spinner eterno.
String mensagemDeErro(Object e) {
  if (e is ErroApi) return e.mensagem;
  // "Sem conexão" com cinco barras de sinal é diagnóstico errado, e errado é pior que nenhum: só
  // afirmamos falta de rede quando o erro é de rede mesmo. Qualquer outra falha (um bug nosso ao
  // montar a requisição, por exemplo) merece uma frase honestamente vaga.
  final rede = e is SocketException || e is TimeoutException || e is http.ClientException;
  return rede
      ? 'Sem conexão. Puxe para tentar de novo.'
      : 'Não deu para carregar. Puxe para tentar de novo.';
}


/// Monta a URL da API convertendo os valores da query para texto.
///
/// Existe separada, e testada, por causa de um defeito que só apareceu no aparelho: `Uri.replace`
/// exige `String` ou `Iterable<String>` em `queryParameters`, e um `page_size: 100` (int) estourava
/// ArgumentError ao MONTAR a requisição. Como o erro não é `ErroApi`, a tela caía no catch genérico
/// e escrevia "sem conexão" — com o wi-fi perfeito e o dashboard carregado ao lado.
///
/// Valor nulo é omitido (filtro não escolhido não vira `?forma=null`), e lista vira parâmetro
/// repetido (`?status=a&status=b`), que é como o backend lê listas.
Uri montarUrl(String base, String caminho, [Map<String, dynamic>? query]) {
  final url = Uri.parse('$base/api/v1$caminho');
  if (query == null || query.isEmpty) return url;
  final limpa = <String, dynamic>{};
  query.forEach((chave, valor) {
    if (valor == null) return;
    limpa[chave] = valor is Iterable
        ? valor.map((v) => '$v').toList()
        : '$valor';
  });
  return limpa.isEmpty ? url : url.replace(queryParameters: limpa);
}
