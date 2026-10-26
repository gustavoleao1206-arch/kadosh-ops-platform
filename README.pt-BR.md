# Kadosh Ops Platform

**Plataforma de operação para uma estética automotiva** — uma API, um banco e um login servindo um
painel web para o dono e um app Android para o sócio que toca o pátio.

🇺🇸 [Read in English](README.md)

```
Painel web (React)     ─┐
                        ├─ HTTPS /api/v1 ─► FastAPI ─► PostgreSQL 16
App Android (Flutter)  ─┘
```

Feito para a Kadosh Detail, estética automotiva de Maceió (AL). Cobre o dia inteiro da loja: o
agendamento, a recepção do carro no balcão, o serviço, o recebimento e os números do fim do mês.
**Situação: em produção** (Docker no Render, PostgreSQL 16). Este repositório é uma cópia pública do
código privado, com os dados reais trocados por exemplos fictícios.

## Funcionalidades

- **Clientes e veículos** — telefone guardado só com dígitos e DDI (duplicado gera aviso), placa
  opcional, normalizada e única entre veículos ativos, e arquivamento em vez de exclusão para o que tem
  histórico.
- **Catálogo de serviços** com preço base e duração estimada, mais **preço combinado por cliente**. O
  valor congela no item da OS: mexer no catálogo nunca reescreve OS antiga.
- **Agenda e ordem de serviço numa entidade só**, com fluxo de status (`orcamento → agendado →
  confirmado → recebido → em_execucao → aguardando_retirada → concluido`, além de `cancelado` /
  `nao_compareceu`). Toda mudança vai para o histórico de eventos na mesma transação.
- **Recepção do veículo numa transação só**: cliente, veículo, OS, serviços combinados e o estado do
  carro na chegada — tudo ou nada, com chave de idempotência gerada no aparelho.
- **Pagamentos**: vários por OS (sinal + restante), uma forma por lançamento, sem pagamento acima do
  saldo, e estorno com motivo obrigatório no lugar de editar ou apagar. O total da OS nunca fica abaixo
  do que já foi recebido.
- **Financeiro**: caixa do dia, extrato e cobrança com situação *derivada* (pago / a receber /
  atrasado), calculada de status, total, recebido e vencimento — nunca gravada.
- **Relatórios**: faturado × recebido (contas diferentes, que nunca se somam), ticket médio, receita
  por serviço, cancelamentos e não comparecimentos, e clientes que sumiram.
- **Dashboard** que reaproveita os mesmos serviços do caixa, dos relatórios e da cobrança, para os
  números baterem ao centavo (um teste confere exatamente isso).
- **Mensagem de "carro pronto" no WhatsApp** (link `wa.me`), com o mesmo texto no painel e no app —
  cada lado tem um teste com a frase literal.
- **Painel web** instalável como PWA; **app Android** com oito telas separadas em *o que fazer*
  (pátio, receber veículo, caixa de hoje, financeiro) e *consultar* (agenda, clientes, catálogo,
  relatórios).
- **Usuários**: o administrador cria contas, redefine senhas e encerra as sessões de um usuário em
  todos os aparelhos.

## Tecnologias

| Camada | Tecnologia |
|---|---|
| API | Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, slowapi, argon2-cffi |
| Banco | PostgreSQL 16 (`unaccent` para busca sem acento) |
| Web | React 19, TypeScript, Vite 8, Tailwind CSS 4, TanStack Query, React Router, Vitest |
| Mobile | Flutter 3.47 / Dart 3 (`http`, `shared_preferences`, `url_launcher`) |
| Entrega | Dockerfile multiestágio (Node compila o painel, Python serve API + painel), Blueprint do Render (`render.yaml`), GitHub Actions |

## Arquitetura

```mermaid
flowchart LR
    W["Painel web<br/>React + Vite (PWA)"] -- "cookie HttpOnly" --> API
    M["App Android<br/>Flutter"] -- "token Bearer" --> API
    subgraph Server["Um serviço Docker"]
        API["FastAPI /api/v1<br/>rotas → serviços → modelos"]
        S["Build do painel servido em /"]
    end
    API --> DB[("PostgreSQL 16")]
```

- `backend/app/api/v1` — rotas finas (57 operações); `backend/app/services` — regras de negócio, onde
  **uma função pública é uma transação** (os auxiliares só fazem `flush()`); `backend/app/models` — 11
  tabelas; `backend/alembic` — migrações, aplicadas antes de cada deploy.
- `web/` — o painel. Mesma origem da API, então não existe CORS.
- `mobile/` — o app do sócio, falando com a mesma API por token Bearer.
- `docs/ARQUITETURA.md` (decisões de projeto) e `docs/RUNBOOK.md` (operação).

## Destaques de engenharia

- **Dinheiro e tempo.** Valores em centavos inteiros de ponta a ponta. Datas `timestamptz` em UTC, e
  "hoje" / "este mês" calculados no fuso da loja (`America/Maceio`) — senão um Pix das 22h fecharia o
  caixa no dia errado.
- **Uma regra, duas implementações, um teste.** A situação de cobrança existe em Python (para a
  resposta) e em SQL (para filtrar e paginar). `test_cobranca.py::test_python_e_sql_concordam` roda as
  duas sobre a mesma matriz de 19 casos e falha se divergirem.
- **Idempotência onde repetir cria valor** (recepção, pagamento, item da OS). Os testes forçam a
  corrida que leva ao ramo do `IntegrityError`, então o código que impede cobrar o cliente duas vezes é
  executado de verdade no CI.
- **Sessão sem JWT.** Token opaco; o banco guarda só o hash SHA-256. Validade deslizante de 30 dias com
  teto absoluto de 90, revogação imediata (logout, "sair de todos os aparelhos", desativação, reset de
  senha). Web: cookie `HttpOnly` + `Secure` + `SameSite=Strict` com checagem anti-CSRF por
  `Sec-Fetch-Site`/`Origin`. App: token Bearer, fora do backup do Android.
- **Limite de login que não vira arma contra o dono.** Três travas: 5 tentativas por minuto por IP;
  atraso progressivo por *origem* (e-mail + IP, IPv6 agrupado por /64), que só freia quem está errando;
  e um teto por conta que vale só para origens de onde a conta nunca entrou. Um atacante sozinho não
  consegue mais manter o dono bloqueado, e a força bruta espalhada por muitos IPs continua contida.
  `tests/test_bloqueio_login.py` simula três horas de um atacante ideal com relógio falso e prova as
  duas metades.
- **Fechado por padrão.** Argon2id, tamanho mínimo de senha imposto em todos os caminhos, CSP sem
  `unsafe-inline`, cabeçalhos `nosniff` / frame / referrer, corpo máximo de 1 MB (inclusive chunked),
  `extra="forbid"` em todo schema, documentação da API desligada em produção, e o app se recusa a subir
  no Render sem `ENV=production`.
- **Deploy seguro.** Migrações no `preDeployCommand` (migração quebrada mantém a versão anterior no
  ar), health check que consulta o banco, o serviço sobe mesmo com o PostgreSQL ainda iniciando, e o
  banco não aceita conexão da internet (`ipAllowList: []`).
- **Erros que se explicam.** Erros de integridade classificados pelo SQLSTATE em 409/422, mensagens de
  validação em português, e um bootstrap do primeiro admin mal configurado escreve no log o comando
  exato para corrigir.

## Rodando localmente

Requisitos: Python 3.11+, PostgreSQL 16 (com a extensão `unaccent` disponível), Node 24. Flutter 3.47
só para o app.

O padrão espera um usuário `kadosh` (senha `kadosh_dev`) e os bancos `kadosh_dev` e `kadosh_test` em
`localhost:5433`; aponte `DATABASE_URL` / `TEST_DATABASE_URL` para outro lugar se preferir.

```bash
# API
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
export DATABASE_URL=postgresql+psycopg://kadosh:kadosh_dev@localhost:5433/kadosh_dev
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.cli seed-demo              # dados de demonstração; recusa produção
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Usuários criados pelo seed: `admin@kadosh.com.br` / `admin12345!` (dono) e
`socio@kadosh.com.br` / `socio12345!` (sócio). Documentação da API em `http://localhost:8000/api/docs`.

```bash
# Painel web — depois do `npm run build`, a própria API o serve em http://localhost:8000/
cd web
npm ci
npm run dev            # http://localhost:5173, com proxy de /api para :8000
npm run build
```

O app Android aponta para `http://10.0.2.2:8000` (a máquina, vista de dentro do emulador), a menos que
seja compilado com `--dart-define=KADOSH_API=https://…`. Os scripts `scripts/*.ps1` automatizam tudo
isso na máquina Windows onde o projeto é desenvolvido.

## Testes

| Suíte | Comando | Resultado |
|---|---|---|
| API (contra PostgreSQL de verdade) | `cd backend && python -m pytest --cov=app --cov-fail-under=95` | **534 testes**, 98% de cobertura |
| Painel web | `cd web && npm test` | **49 testes** em 4 arquivos |
| App Android | `cd mobile && flutter test` | **72 testes** |

A suíte da API cria o schema pelos modelos, limpa as tabelas entre testes e se recusa a rodar num banco
cujo nome não termine em `_test`. O CI (`.github/workflows/ci.yml`) roda as três suítes em todo pull
request, mais `alembic upgrade → check → downgrade → upgrade` para provar que as migrações batem com os
modelos e são reversíveis, `npm run build` (com checagem de tipos) e `flutter analyze`.

## Licença

Código sob a [licença MIT](LICENSE). Os nomes, logos e ícones **Kadosh**, e os textos e preços do
negócio usados como dados de exemplo, não estão incluídos — veja o aviso de marca no arquivo da licença.
