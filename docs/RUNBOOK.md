# Runbook — o que fazer quando…

## …esqueci a senha do admin
No Shell do serviço no Render (ou localmente em `backend/`):

```
python -m app.cli reset-password voce@exemplo.com
```

Imprime uma senha temporária uma única vez; o próximo login obriga a trocar. Todas as sessões são encerradas.
**Não reativa** um usuário desativado — reativar é decisão do admin, no painel. Limpe o histórico do terminal depois.

**Copie a senha antes de sair da aba.** O Shell do Render é um terminal efêmero: recarregar a
página, trocar de aba lateral ou deixar a sessão expirar apaga tudo o que foi impresso, e não há
como pedir a mesma senha de novo — ela só existiu naquela linha. Se perder, rode o comando outra
vez; ele gera uma nova e invalida a anterior. Isso vale para `reset-password` e para
`create-user`, que também imprimem a senha uma única vez.

## …quero trocar o e-mail do administrador (e o login falha)

**Trocar `ADMIN_EMAIL` no painel do Render NÃO cria uma conta nova.** Aconteceu no dia do deploy: o
e-mail foi trocado, o serviço reiniciou, e o login passou a responder "e-mail ou senha inválidos"
sem explicar nada — o que parece problema de senha e é problema de cadastro.

O motivo é uma regra deliberada: o bootstrap só cria o **primeiro** administrador, quando a tabela
de usuários está VAZIA. Com alguém já cadastrado ele não mexe em nada, para que um redeploy nunca
devolva senha antiga nem ressuscite acesso removido.

Para criar de verdade a conta nova, no Shell do serviço:

```
python -m app.cli create-user "Seu Nome" novo@email.com admin
```

Imprime uma senha temporária uma única vez; o próximo login obriga a trocar. Depois, remova a conta
antiga pelo painel (Configurações → usuários) e limpe o histórico do terminal.

Duas coisas que travam esse caminho, e as duas agora aparecem no log do Render:

- **Senha com menos de 10 caracteres** em `ADMIN_PASSWORD`: o bootstrap recusa e não cria nada.
- **`ADMIN_EMAIL` apontando para alguém que não existe**, com a tabela já preenchida: o log diz o
  e-mail, quantos usuários existem e o comando exato acima.

Depois do primeiro login, `ADMIN_EMAIL` e `ADMIN_PASSWORD` não servem para mais nada — remova as
duas do Environment.

## …limpeza periódica de sessões antigas
```
python -m app.cli purge-sessions
```
Remove sessões revogadas ou expiradas há mais de 30 dias (pode ir no pre-deploy do Render).

## …quero criar um usuário sem usar o painel
```
python -m app.cli create-user "Nome" email@exemplo.com staff
```

## …o sócio perdeu o celular
Painel → Configurações → usuário → **Sair de todos os aparelhos** (ou desativar o usuário). Efeito imediato.

## …o banco local não sobe
```
scripts\db.ps1 status
type X:\dev\pgdata\server.log
```
Porta em uso? O projeto usa **5433** (a 5432 está ocupada por outro programa nesta máquina).
Reinstalar do zero: apague `X:\dev\pgdata`, rode `X:\dev\pgsql\bin\initdb -D X:\dev\pgdata -U postgres -W -E UTF8 --locale=C`,
ajuste `port = 5433` em `postgresql.conf`, inicie e recrie o usuário e os bancos:

```sql
CREATE ROLE kadosh LOGIN PASSWORD 'kadosh_dev';
CREATE DATABASE kadosh_dev OWNER kadosh;
CREATE DATABASE kadosh_test OWNER kadosh;
```

## …preciso de uma nova migration
1. Altere os modelos em `backend/app/models/`.
2. `backend\.venv\Scripts\python -m alembic revision --autogenerate -m "descreva a mudança"`
3. **Leia o arquivo gerado** em `backend/alembic/versions/` antes de aplicar.
4. `backend\.venv\Scripts\python -m alembic upgrade head`
5. Em produção: faça backup antes (ver abaixo); a migration roda no pre-deploy do Render.

## …backup e restauração (fase 10 completa este item)
```
scripts\backup.ps1            # gera backups\kadosh-AAAA-MM-DD.dump
```
Restaurar num banco vazio: `pg_restore -d <DATABASE_URL> --no-owner backups\kadosh-....dump`.

**Produção não aceita conexão de fora** (`ipAllowList: []` no `render.yaml`). Para o `pg_dump` pela
URL externa, libere o seu IP em Render → kadosh-db → Networking, rode o backup e **apague a regra**
logo depois — liberação "temporária" esquecida é como um banco fica aberto sem ninguém perceber.
O dump tem nome, telefone e placa de clientes: guarde-o cifrado, nunca em pasta sincronizada em
texto claro.

## …onde está a chave de assinatura do APK (fase 7)
Gerenciador de senhas + cópia no Drive. Sem ela, atualizar o app obriga o sócio a desinstalar.

Hoje o `buildTypes.release` ainda assina com a chave de **debug** (padrão do template do Flutter).
Serve para instalar no celular do sócio pelo lado; não serve para a Play Store.

## …como gerar o APK
```
scripts\apk.ps1              # release (o que o sócio instala)
scripts\apk.ps1 -Debug       # debug, para diagnóstico
scripts\apk.ps1 -Api https://kadosh.onrender.com
```
O `-Api` vira `--dart-define=KADOSH_API=...`. Sem ele o app aponta para `http://10.0.2.2:8000`,
que é o host da máquina visto de dentro do emulador — **não funciona num celular de verdade**.

Instalar no aparelho: mande o `.apk` por WhatsApp/Drive, abra no celular e autorize "instalar de
fontes desconhecidas" para o app que estiver abrindo o arquivo.

## …quero testar o app num emulador Android
```
scripts\instalar-emulador.ps1     # uma vez: emulador + imagem do Android 35 (~2 GB)
scripts\dev.ps1 -Seed             # backend com dados de demonstração
scripts\apk.ps1 -Api http://10.0.2.2:8000
scripts\emulador.ps1 -Instalar
```
Entre como `socio@kadosh.com.br` / `socio12345!` (o app é do sócio).

Dentro do emulador, `10.0.2.2` é o PC. O `dev.ps1` já sobe o uvicorn em `0.0.0.0`, então funciona
sem túnel e sem mexer no firewall.

O AVD fica em `X:\dev\avd`, não no perfil do usuário: são vários GB e o SSD principal está apertado.
Aceleração por WHPX (`emulator -accel-check` confirma). Ver a tela por linha de comando:
```
adb shell screencap -p /sdcard/t.png && adb pull /sdcard/t.png tela.png
```
Use `pull`, não `>`: o `>` do PowerShell corrompe binário (mete BOM no PNG).

## …o app diz "Sem conexão com o servidor" e a API está no ar
**Confira a permissão de internet antes de acusar a rede.**
```
aapt2 dump permissions app-release.apk
```
Tem de listar `android.permission.INTERNET`. O template do Flutter declara essa permissão só em
`src/debug` e `src/profile`; o `src/main` — que é o que vale no release — sai sem ela. O app
instala, abre, desenha tudo e nunca conecta, sem nenhuma pista de que o problema é permissão.

Aconteceu aqui, e custou caro no diagnóstico: a primeira suspeita foi o Firewall do Windows, que não tinha
nada a ver. O `apk.ps1` agora recusa entregar um APK sem a permissão, e o manifesto em
`mobile/android/app/src/main/AndroidManifest.xml` traz o comentário explicando por que a linha existe.

Nada disso é pego por `flutter analyze`, pelos testes do app, pelos testes do backend ou pelo CI —
nenhum deles instala o APK. Só aparece rodando no aparelho.

## …um script .ps1 dá erro de sintaxe estranho
Salve como **UTF-8 com BOM**. O PowerShell 5.1 lê `.ps1` sem BOM como ANSI; aí um travessão `—`
vira `â€"`, e o `0x94` desse lixo é uma aspa curva que o PowerShell aceita como delimitador de
string — a partir dali o parser se perde e reclama de linhas que estão corretas.

## …o build Android quebra nesta máquina (e por quê)
Três defeitos de ambiente, todos já corrigidos. Se voltarem, é aqui que está o mapa.

**1. "Unable to establish loopback connection" (Gradle nem começa)**
O JDK 17 cria um socket AF_UNIX para o `Pipe.open()`, e o coloca dentro do `%TEMP%` do usuário.
Nesta máquina esse arquivo nasce mas **não pode ser reaberto** — `connect` volta com
`SocketException: Invalid argument` (WSAEINVAL). O `PipeImpl` do JDK só tem plano B se o *bind*
falhar, nunca se o *connect* falhar, então o erro sobe disfarçado de problema de rede. Não é rede:
TCP de loopback funciona normalmente aqui.

Correção, permanente e em um lugar só — `X:\dev\tools\jdk17\conf
et.properties`:
```
jdk.net.unixdomain.tmpdir=X:/dev/tmp
```
Barra normal de propósito: neste arquivo a contrabarra é escape. Backup em `net.properties.bak`.
Para conferir: `java X:\dev\DiagPipe.java` tem de imprimir "Pipe.open() FUNCIONOU".

Sintoma colateral: sobram arquivos `socket_*` de 0 byte no `%TEMP%` (havia 29 quando o problema
foi encontrado). Depois da correção param de aparecer.

**2. `sdkmanager` morre com 0xC0000409 e o build pede um NDK**
O plugin do Flutter exige um NDK em toda build Android, mesmo sem código nativo — e ele mesmo roda
`sdkmanager --install ndk;<versão>` para baixá-lo. Nesta máquina toda a CLI do SDK morre com
`0xC0000409` (`sdkmanager`, `android sdk install` e `android sdk list`).

Não adianta tirar o `ndkVersion` do `build.gradle.kts` (o plugin reinjeta) nem pôr
`android.builder.sdkDownload=false` (quem baixa é o Flutter, não o AGP). O caminho é instalar o NDK
na mão — o plugin checa se a versão já existe e, se existir, nem chama o `sdkmanager`:
```
scripts\instalar-ndk.ps1
```
A URL sai do próprio repositório do Google (`repository2-3.xml`); são ~700 MB.

**3. "Could not close incremental caches" no Kotlin**
O compilador Kotlin não consegue fechar os arquivos `.tab` de cache incremental — um antivírus
segurando o handle na hora de fechar. Resolvido com `kotlin.incremental=false` em
`mobile/android/gradle.properties`.

## …uma OS antiga apareceu como "atrasada" depois da fase 8

Não é bug. A régua de cobrança (`services/billing.py`) diz que **OS concluída com saldo em aberto e
sem vencimento é atrasada** — entregou o carro, não recebeu e não combinou data. Ao aplicar a
migration `c4a1f7b20e58` numa base com histórico, todas as OS nessa situação passam a aparecer no
vermelho de uma vez.

Para tirar uma do vermelho, defina o prazo combinado (o único campo que uma OS concluída aceita):

```
PATCH /api/v1/work-orders/{id}  {"vencimento": "2026-09-20T18:00:00"}
```

Ela volta para "a receber" até o prazo chegar. Se o dinheiro nunca vai entrar, o caminho é estornar
ou ajustar o desconto — nunca apagar.

## …os números do dashboard batem com o caixa?

Têm de bater, ao centavo. O `/dashboard` **não faz conta nenhuma**: ele chama os mesmos serviços do
caixa (`payments.recebido_centavos`), do relatório (`reports.totais`), da agenda
(`work_orders.contadores_do_dia`) e da cobrança (`billing.resumo`). Se um dia divergirem, o bug é de
reuso — alguém criou uma segunda conta em vez de chamar a existente.

O teste que guarda isso é `tests/test_financeiro.py::test_caixa_extrato_relatorio_e_dashboard_fecham`:
o mesmo dinheiro, com estorno e desconto no meio, contado por caixa, extrato, relatório, série
mensal e dashboard — todos têm de dar o mesmo número.

## …o filtro de cobrança mostra uma OS que, aberta, se diz outra coisa

Isso seria o pior bug do módulo, e existe um teste só para ele. A régua está escrita duas vezes —
`billing.situacao` (Python, para a resposta) e `billing.situacao_sql` (SQL, para filtrar e paginar) —
porque peneirar em Python devolveria "página 1 de 50" com 6 linhas.

Se você alterar uma, **altere a outra**. `tests/test_cobranca.py::test_python_e_sql_concordam` roda
as duas sobre a mesma matriz de 19 casos e falha na hora se divergirem.

## …o app diz "sem conexão" mas o wi-fi está bom

Antes de culpar a rede, desconfie da REQUISIÇÃO. Já aconteceu duas vezes por motivos diferentes:

1. **502 em HTML** (proxy do Render, portal cativo de wi-fi): o `jsonDecode` estourava antes de
   olhar o status. Resolvido em `_resposta`, que lê o status primeiro.
2. **Valor não-texto na query** (`page_size: 100` como inteiro): `Uri.replace` exige
   `String`/`Iterable<String>` e estourava ao MONTAR a URL. Resolvido em `montarUrl`, com teste.

Hoje `mensagemDeErro` só escreve "Sem conexão" para erro de rede de verdade
(`SocketException`, `TimeoutException`, `ClientException`). Qualquer outra falha aparece como
"Não deu para carregar" — vago de propósito, porque diagnóstico errado é pior que nenhum.

Para ver o erro real:

```bash
X:/dev/tools/android-sdk/platform-tools/adb.exe logcat -s flutter
```

## …a data no app está um dia à frente (ou atrás) da do painel

O app formata no fuso da LOJA (`noFusoDaLoja`, −3h fixo), não no do aparelho. Se um vencimento
marcado para 25/09 aparecer como 26/09, a conversão foi pulada em algum ponto: um vencimento é
gravado às 23:59 em Maceió, então bastam minutos de diferença para o dia virar.

Toda exibição de data e hora tem de passar por `data()` ou `hora()` de `modelos.dart`. Usar
`DateTime.toLocal()` direto na tela mostra o relógio do celular, que só por acaso é o da loja.

## …o script .ps1 morre com o trabalho já feito

PowerShell 5.1 com `$ErrorActionPreference = "Stop"` transforma **qualquer linha de stderr** de um
executável em erro terminante. O `flutter build` escreve avisos no stderr (o clássico
"SDK XML version 4 was encountered") e o `apk.ps1` morria com o APK pronto no disco.

Nos scripts, quem manda é o código de saída, não o stderr:

```powershell
$antes = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& flutter @args
$codigo = $LASTEXITCODE
$ErrorActionPreference = $antes
if ($codigo -ne 0) { exit $codigo }
```


## …o sócio precisa entrar de novo a cada três meses

É a regra, não defeito. A sessão renova sozinha enquanto o app é usado, mas só até 90 dias contados
do login (`SESSION_ABSOLUTE_DAYS`). Sem esse teto, um token que vazasse — pelo backup de um celular
antigo, por um `curl` copiado num grupo — valeria para sempre, bastando uma requisição por mês para
mantê-lo vivo. E não haveria como perceber: não existe tela que liste as sessões abertas.

Para encurtar ou alongar, mude `SESSION_ABSOLUTE_DAYS` no ambiente. Para cortar o acesso agora:
Painel → Configurações → usuário → **Sair de todos os aparelhos**.

## …trocar o celular do sócio

O app **não** entra no backup do Android (o manifesto declara `allowBackup="false"` e regras de
extração que excluem `shared_prefs`, para nuvem e para transferência direta). Isso é de propósito: o
token de sessão mora ali em texto puro, e restaurar o backup noutro aparelho daria acesso à API como
o sócio.

Consequência prática: no celular novo ele entra de novo com e-mail e senha. É o comportamento certo.

Conferir num APK pronto:

```
aapt2 dump xmltree --file AndroidManifest.xml app-release.apk | findstr allowBackup
```

## …gerar o APK que vai para o celular do sócio

O endereço do servidor entra no BINÁRIO, e o script recusa as duas formas de errar isso:

```
scripts\apk.ps1 -Api https://SEU-APP.onrender.com   # o que o sócio instala
scripts\apk.ps1 -Emulador                           # só para o emulador desta máquina
```

Sem `-Api` e sem `-Emulador` ele para: um release padrão sairia apontando para `http://10.0.2.2:8000`
(o host visto de dentro do emulador) e não conectaria em celular nenhum. Com `http://` fora da rede
local ele também para — o login manda e-mail e senha no corpo, e em texto puro na internet isso é
entregar a senha.

## …escrever caminho do Windows na documentação

Cuidado com a barra invertida. Um caminho escrito dentro de uma string que passa por mais uma camada
de interpretação de escape se corrompe em silêncio: `\a` vira campainha (0x07), `\t` vira
tabulação, e `\b`, `\f`, `\v`, `\0` também têm significado.

Já aconteceu aqui: dez linhas da documentação traziam `scripts\apk.ps1` como
`scripts` + campainha + `pk.ps1`, e `X:\dev\avd` como `X:\dev` + campainha + `vd`. No
editor parece certo — o byte é invisível —, mas quem copiasse a linha rodava um comando inexistente.

`backend/tests/test_documentacao.py` agora quebra o build se isso voltar. Ao escrever documentação
com caminhos, use uma ferramenta que não reinterprete escapes, ou monte a barra com `chr(92)`.


## …rodar os testes das três camadas

```
scripts\test.ps1                  # backend, contra o Postgres local da porta 5433
cd web && npm test                # painel
cd mobile && flutter test         # app
```

Cobertura do backend, com o mesmo piso que o CI aplica:

```
cd backend && .venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing --cov-fail-under=95
```

O piso de 95% pega a regressão grande — um serviço inteiro entrando sem teste. Não é para chegar a
100%: quando o número vira a meta, escreve-se teste para a linha e não para o comportamento.

## …por que existem testes que "cegam" uma função

`test_corridas_e_bordas.py` e `test_recepcao_bordas.py` substituem `_mesma_chave` por uma versão que
responde "não existe" nas primeiras chamadas. Parece truque, e é — mas é o único jeito de exercitar
o `except IntegrityError` do pagamento e da recepção.

Esses dois blocos são a última rede contra **cobrar o cliente duas vezes** e **abrir duas OS para o
mesmo carro**, e só rodam quando duas requisições disputam a mesma chave de idempotência com um
tempo específico entre elas. Numa suíte sequencial isso nunca acontece por acaso: até esta fase, as
duas linhas mais importantes do sistema nunca tinham sido executadas por teste nenhum.

Se você mexer na idempotência, rode estes dois arquivos e confira que a asserção
`chamadas["n"] >= 3` (ou `>= 2`) continua valendo — ela existe para o teste falhar em vez de passar
sem ter exercitado nada.

## …a mensagem de WhatsApp está diferente no app e no painel

Não deveria: `web/src/features/work-orders/mensagens.ts` e `mobile/lib/mensagens.dart` montam o
MESMO texto, e cada um tem um teste com a frase literal. Se os dois arquivos divergirem, um dos
testes falha — que é a única forma de perceber antes do cliente, que receberia mensagens diferentes
conforme quem avisou.


## …onde o sistema está no ar

**https://kadosh-ops.onrender.com** — painel e API no mesmo serviço.

No Render (workspace do dono), em **Virgínia**:

| Recurso | O que é | Plano |
|---|---|---|
| `kadosh-ops` | serviço web (Docker) | Starter |
| `kadosh-db` | PostgreSQL 16 | Basic-256mb |

Virgínia: é a região mais próxima de Maceió entre as que o Render oferece.
Banco e serviço PRECISAM ficar na mesma — em regiões diferentes o tráfego sai para a internet e
some a rede privada.

O Postgres está no menor plano **pago** de propósito: o gratuito expira em 30 dias e leva o banco
junto, o que é inaceitável para dados financeiros.

## …entrar pela primeira vez

A senha do primeiro administrador foi **gerada pelo Render**, não escolhida por ninguém. Ela está em:

    Render → kadosh-ops → Environment → ADMIN_PASSWORD

O usuário é o e-mail em `ADMIN_EMAIL`. A conta nasce exigindo troca de senha no primeiro login.

**Depois de entrar e trocar a senha, REMOVA `ADMIN_EMAIL` e `ADMIN_PASSWORD` do Environment.**
Deixá-las não reabre nada (o bootstrap só roda com a tabela de usuários vazia), mas senha guardada
em variável de ambiente sem motivo é dívida esperando a próxima pessoa.

## …o deploy falhou, e agora

O Render mantém a versão anterior servindo quando um deploy falha — o site não cai. Para achar o
motivo: **Render → kadosh-ops → Logs**, e leia de baixo para cima.

Dois pontos onde ele reprova de propósito:

- `preDeployCommand` (`alembic upgrade head`) — migração quebrada aborta antes de trocar a versão.
- `healthCheckPath` (`/api/v1/health`) — o serviço tem de responder 200, e a rota consulta o banco.

Se a mensagem for `connection refused` na porta 5432, é o banco ainda subindo: a partir do commit
4bfb536 isso não derruba mais o serviço (espera 30s e sobe assim mesmo), mas o `/health` vai acusar
`db` fora até o Postgres voltar.

## …subir uma versão nova

`git push origin main`. O Render acompanha a branch e reimplanta sozinho (`autoDeploy: true`), e o
CI roda em paralelo no GitHub. Não há passo manual.

Para reimplantar sem commit (raro): Render → kadosh-ops → **Manual Deploy**.

## …gerar o APK que o sócio instala agora que está em produção

```
scripts\apk.ps1 -Api https://kadosh-ops.onrender.com
```

O arquivo sai em `mobile\build\app\outputs\flutter-apk\app-release.apk`. Mande por
WhatsApp ou Drive; no celular, autorize "instalar de fontes desconhecidas" para o app que abrir o
arquivo.

Confira antes de mandar (o script já faz a primeira, as outras são para auditoria):

```
aapt2 dump permissions app-release.apk | findstr INTERNET
aapt2 dump xmltree --file AndroidManifest.xml app-release.apk | findstr allowBackup
```


## …o que o app do sócio tem, e por que não tem o resto

Oito telas, em dois grupos que a própria home separa:

**O QUE FAZER** — muda a loja: **Pátio**, **Receber veículo**, **Caixa de hoje**, **Financeiro**
(extrato e cobranças).

**CONSULTAR** — só responde pergunta: **Agenda**, **Clientes**, **Catálogo**, **Relatórios**.

A divisão não é de gosto. Quem está com a mão ocupada procura na primeira lista; quem está ao
telefone com o cliente, na segunda.

O que o app **não** faz, e o motivo de cada um:

| Não tem | Por quê |
|---|---|
| Criar e editar serviço do catálogo | O servidor exige administrador (`POST/PATCH/DELETE /services`). Botão ali daria 403 na cara do sócio. Preço é decisão do dono. |
| Preço combinado de cliente | Mesma regra do servidor. E a tela de catálogo responde "quanto custa": um valor que vale só para uma pessoa, mostrado fora da ficha dela, é o caminho curto para cobrar o desconto do outro. |
| Marcar e remarcar agendamento | A agenda do app é só leitura. Agendar pede teclado, calendário e a visão da semana — fazer isso no celular, no meio do pátio, é o caminho curto para agendar no dia errado. |
| Cadastrar cliente avulso | Cliente novo nasce em "Receber veículo", que abre cliente, veículo e OS numa transação só. Um segundo caminho é como aparece cadastro repetido. |
| Corrigir cadastro (nome, telefone) | Painel, com teclado de verdade. |

**A agenda de um dia inclui carro que já está no pátio** — o servidor faz isso de propósito
(`_no_dia`, terceira cláusula: "carro que ainda está no pátio aparece todo dia, até sair"). Por isso
a tela separa "a chegar" de "na loja agora" e, num dia que já passou, troca os rótulos: "a chegar"
descreveria gente que não chega mais.

## …quero o sistema no meu iPhone

**Não existe app iOS, e não vai existir tão cedo.** Compilar para iPhone exige macOS com Xcode —
é limitação da Apple, não do Flutter, e não há como contornar no Windows. Instalar por cabo depende
do mesmo Mac (Xcode ou Apple Configurator). Um app nativo custaria ainda uma conta de desenvolvedor
Apple (US$ 99/ano) ou, na conta gratuita, reinstalar tudo **a cada 7 dias**.

O caminho é o painel, que é a ferramenta do dono de qualquer forma — o app Android é o subconjunto
do sócio (ver a seção abaixo sobre o que ele tem).

**Para instalar:** no iPhone, abra https://kadosh-ops.onrender.com no **Safari** (só o Safari; o
Chrome no iOS não instala), toque em **Compartilhar** e em **Adicionar à Tela de Início**.

Fica um ícone com o K da marca, abre em tela cheia sem barra de endereço, e atualiza sozinho a cada
deploy. Sem Mac, sem conta Apple, sem cabo e sem expirar.

### O que foi preciso para isso funcionar

- A barra lateral de 232px vira **gaveta** abaixo de 1024px (`AppShell`). É a MESMA árvore de
  navegação, não uma segunda lista — duas divergem no dia em que alguém acrescenta uma tela.
- `viewport-fit=cover` + as classes `.safe-top` / `.safe-bottom`: sem elas o conteúdo passa por
  baixo da faixa de status e da barra de gestos.
- Campos com **16px em telas de toque**. Abaixo disso o Safari dá zoom sozinho ao focar um campo e
  **não desfaz** — a tela trava torta no meio de um lançamento de pagamento.
- `apple-touch-icon` em **PNG**: o iOS ignora SVG aqui. Gerado por `scripts\gerar-icones.py`,
  que só precisa rodar de novo se o desenho mudar.

`web/src/pwa.test.ts` verifica que o manifesto continua válido e que todo ícone declarado existe —
a falha aqui é silenciosa: o site abre normal e o navegador só deixa de oferecer a instalação.
