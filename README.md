# Kadosh Ops Platform

**Operations platform for a car detailing business** — one API, one database and one login serving a
web back office for the owner and an Android app for the partner who runs the shop floor.

🇧🇷 [Leia em português](README.pt-BR.md)

```
Web panel (React)      ─┐
                        ├─ HTTPS /api/v1 ─► FastAPI ─► PostgreSQL 16
Android app (Flutter)  ─┘
```

Built for Kadosh Detail, a car detailing shop in Maceió, Brazil. It covers the whole day of the shop:
booking, receiving the car at the counter, the work itself, getting paid, and the numbers at the end of
the month. **Status: in production** (Docker on Render, PostgreSQL 16). This repository is a public
snapshot of the private codebase, with real data replaced by fictitious samples.

## Context for non-Brazilian readers

The code, comments and screens are in Portuguese. A short glossary:

| Term | Meaning |
|---|---|
| **OS** (*ordem de serviço*) | Work order. In this system the appointment and the work order are the same entity. |
| **Pátio** | The shop yard: the cars that are physically in the shop right now. |
| **Recepção** | Vehicle intake at the counter (creates client, vehicle and work order in one step). |
| **Pix** | Brazil's instant payment system, run by the Central Bank. The most common way customers pay. |
| **Estorno** | Reversal of a payment. Payments are never edited or deleted, only reversed. |
| **Fiado / vencimento** | Informal store credit / due date. A finished job can be delivered unpaid with an agreed date. |
| **Sócio** | Business partner. In the app it is the `staff` role; the owner is `admin`. |
| **Placa Mercosul** | Brazilian license plate format (`ABC1D23`). Stored normalized, searchable by fragment. |

## Features

- **Clients and vehicles** — phone stored as digits with country code (duplicates trigger a warning),
  optional plate normalized and unique among active vehicles, archive instead of delete for anything
  with history.
- **Service catalog** with base price and estimated duration, plus **per-client negotiated prices**.
  The price is frozen on the work order item, so editing the catalog never rewrites past orders.
- **Scheduling and work orders in one entity** with a status flow (`orcamento → agendado → confirmado →
  recebido → em_execucao → aguardando_retirada → concluido`, plus `cancelado` / `nao_compareceu`).
  Every change is written to an event log in the same transaction.
- **Vehicle intake in a single transaction**: client, vehicle, work order, agreed services and the
  condition of the car on arrival — all or nothing, with an idempotency key generated on the device.
- **Payments**: several per order (deposit + balance), one method per entry, no overpayment, and a
  reversal with a mandatory reason instead of edit or delete. The order total can never drop below what
  was already received.
- **Finance**: today's cash, statement, and receivables with a *derived* status (paid / to receive /
  overdue) computed from status, total, received amount and due date — never stored.
- **Reports**: billed vs. received (two different numbers, never added together), average ticket,
  revenue per service, cancellations and no-shows, and customers who stopped coming back.
- **Dashboard** that reuses the same services as cash, reports and billing, so the numbers match to the
  cent (there is a test that checks exactly that).
- **"Your car is ready" WhatsApp message** (`wa.me` link), with the same text in the web panel and in
  the app — each side has a test with the literal sentence.
- **Web panel** installable as a PWA; **Android app** with eight screens split into *what to do*
  (yard, intake, today's cash, finance) and *what to look up* (agenda, clients, catalog, reports).
- **User management**: admin creates users, resets passwords and can sign a user out of every device.

## Tech stack

| Layer | Technology |
|---|---|
| API | Python 3.11, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, slowapi, argon2-cffi |
| Database | PostgreSQL 16 (`unaccent` for accent-insensitive search) |
| Web | React 19, TypeScript, Vite 8, Tailwind CSS 4, TanStack Query, React Router, Vitest |
| Mobile | Flutter 3.47 / Dart 3 (`http`, `shared_preferences`, `url_launcher`) |
| Delivery | Multi-stage Dockerfile (Node builds the panel, Python serves API + panel), Render Blueprint (`render.yaml`), GitHub Actions |

## Architecture

```mermaid
flowchart LR
    W["Web panel<br/>React + Vite (PWA)"] -- "HttpOnly cookie" --> API
    M["Android app<br/>Flutter"] -- "Bearer token" --> API
    subgraph Server["One Docker service"]
        API["FastAPI /api/v1<br/>routers → services → models"]
        S["Built panel served at /"]
    end
    API --> DB[("PostgreSQL 16")]
```

- `backend/app/api/v1` — thin routers (57 operations); `backend/app/services` — business rules, where
  **one public function is one transaction** (helpers only `flush()`); `backend/app/models` — 11 tables;
  `backend/alembic` — migrations, applied before each deploy.
- `web/` — the back office. Same origin as the API, so there is no CORS at all.
- `mobile/` — the partner's app, talking to the same API with a Bearer token.
- `docs/ARQUITETURA.md` (design decisions) and `docs/RUNBOOK.md` (operations), in Portuguese.

## Engineering highlights

- **Money and time.** Amounts are integer cents end to end. Timestamps are `timestamptz` in UTC, and
  "today" / "this month" are computed in the shop's time zone (`America/Maceio`) — otherwise a Pix
  received at 10 p.m. would close the cash register on the wrong day.
- **One rule, two implementations, one test.** The billing status exists in Python (for responses) and
  in SQL (for filtering and pagination). `test_cobranca.py::test_python_e_sql_concordam` runs both over
  the same 19-case matrix and fails if they ever disagree.
- **Idempotency where repeating creates value** (intake, payments, order items). The tests force the
  race that leads to the `IntegrityError` branch, so the code that prevents charging a customer twice is
  actually executed in CI.
- **Sessions without JWT.** Opaque tokens; the database stores only their SHA-256 hash. 30-day sliding
  validity with a 90-day absolute cap, immediate revocation (logout, "sign out of all devices",
  deactivation, password reset). Web: `HttpOnly` + `Secure` + `SameSite=Strict` cookie with a
  `Sec-Fetch-Site`/`Origin` CSRF check. App: Bearer token, excluded from Android backups.
- **Login throttling that can't be turned against the owner.** Three layers: 5 attempts per minute per
  IP; a progressive delay per *source* (e-mail + IP, IPv6 grouped by /64) that only slows down whoever
  is failing; and a per-account cap that applies only to sources the account has never logged in from.
  A single attacker can no longer keep the owner locked out, and brute force spread over many IPs is
  still capped. `tests/test_bloqueio_login.py` simulates three hours of an optimal attacker with a fake
  clock and proves both halves.
- **Closed by default.** Argon2id, minimum password length enforced on every path, CSP without
  `unsafe-inline`, `nosniff` / frame / referrer headers, 1 MB body limit (chunked requests included),
  `extra="forbid"` on every schema, API docs disabled in production, and the app refuses to start on
  Render unless `ENV=production`.
- **Safe deploys.** Migrations run in `preDeployCommand` (a failed migration keeps the old version
  online), the health check queries the database, the service still boots if PostgreSQL is not ready
  yet, and the database accepts no connection from the internet (`ipAllowList: []`).
- **Errors that explain themselves.** Integrity errors are mapped by SQLSTATE to 409/422, validation
  messages are translated, and a misconfigured first-admin bootstrap writes the exact fix to the log.

## Running locally

Requirements: Python 3.11+, PostgreSQL 16 (with the `unaccent` contrib extension available), Node 24.
Flutter 3.47 only for the mobile app.

The defaults expect a `kadosh` role (password `kadosh_dev`) and the databases `kadosh_dev` and
`kadosh_test` on `localhost:5433`; point `DATABASE_URL` / `TEST_DATABASE_URL` elsewhere if you prefer.

```bash
# API
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
export DATABASE_URL=postgresql+psycopg://kadosh:kadosh_dev@localhost:5433/kadosh_dev
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.cli seed-demo              # demo data; refuses to run in production
.venv/bin/python -m uvicorn app.main:app --port 8000
```

Demo users created by the seed: `admin@kadosh.com.br` / `admin12345!` (owner) and
`socio@kadosh.com.br` / `socio12345!` (partner). API docs at `http://localhost:8000/api/docs`.

```bash
# Web panel — after `npm run build`, the API also serves it at http://localhost:8000/
cd web
npm ci
npm run dev            # http://localhost:5173, proxying /api to :8000
npm run build
```

The Android app points at `http://10.0.2.2:8000` (the host machine, seen from the emulator) unless
built with `--dart-define=KADOSH_API=https://…`. The `scripts/*.ps1` helpers wrap all of this on the
Windows machine where the project is developed.

## Tests

| Suite | Command | Result |
|---|---|---|
| API (against a real PostgreSQL) | `cd backend && python -m pytest --cov=app --cov-fail-under=95` | **534 tests**, 98% coverage |
| Web panel | `cd web && npm test` | **49 tests** in 4 files |
| Android app | `cd mobile && flutter test` | **72 tests** |

The API suite creates its schema from the models, truncates between tests and refuses to run against a
database whose name does not end in `_test`. CI (`.github/workflows/ci.yml`) runs the three suites on
every pull request, plus `alembic upgrade → check → downgrade → upgrade` to prove migrations match the
models and are reversible, `npm run build` (type check included) and `flutter analyze`.

## License

Source code under the [MIT License](LICENSE). The **Kadosh** names, logos and icons, and the business
texts and prices used as sample data are not covered by it — see the brand notice in the license file.
