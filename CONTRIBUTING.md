# Contributing

Thanks for taking the time to look at the code. Bug reports, questions and pull requests are welcome.
Security problems go through the private channel described in [SECURITY.md](SECURITY.md), never
through a public issue.

## Workflow

1. **Fork** the repository and clone your fork.
2. Create a **branch** from `main` with a descriptive name (`fix/receivables-overdue-filter`,
   `feat/report-export`…).
3. Make the change **with tests** — a bug fix comes with a test that fails without it.
4. Run the three suites below, then open a **pull request** against `main` explaining *what* changed
   and *why*. CI runs the same checks on every pull request.

## Setting up and running the tests

The backend tests run against a real PostgreSQL 16 database whose name ends in `_test` (the suite
refuses any other). Defaults: `postgresql+psycopg://kadosh:kadosh_dev@localhost:5433/kadosh_test`;
override with `TEST_DATABASE_URL`.

```bash
# backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest --cov=app --cov-fail-under=95

# migrations must match the models and be reversible (same steps as CI)
export DATABASE_URL=postgresql+psycopg://kadosh:kadosh_dev@localhost:5433/kadosh_test
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m alembic check
.venv/bin/python -m alembic downgrade base
.venv/bin/python -m alembic upgrade head

# web panel
cd web
npm ci
npm run build          # includes the TypeScript check
npm test

# Android app
cd mobile
flutter pub get
flutter analyze
flutter test
```

## Conventions that the code relies on

Code, comments, commit messages and UI text are in Brazilian Portuguese — please keep it that way.

- **Money is integer cents.** Never floats, in any layer.
- **Dates:** `timestamptz` in UTC in the database; "today", "this week" and "this month" are computed
  in `APP_TIMEZONE` (`America/Maceio`).
- **Transactions:** one public function in `backend/app/services/` is one transaction and does the
  `commit`. Internal helpers only `flush()`.
- **Work order history:** every change to a work order (status, discount, item, payment) writes a
  `work_order_events` row in the same transaction.
- **Derived, not stored:** the billing status is computed. It exists in Python
  (`billing.situacao`) and in SQL (`billing.situacao_sql`); change one, change the other —
  `tests/test_cobranca.py::test_python_e_sql_concordam` checks they agree.
- **Payments are never edited or deleted** — they are reversed (with a reason) and entered again.
- **Schemas reject unknown fields** (`extra="forbid"`); integrity errors are classified centrally in
  `main.py` by SQLSTATE, so routes don't catch `IntegrityError`.
- **New migration:** change the models, run `alembic revision --autogenerate -m "..."`, **read** the
  generated file, then `alembic upgrade head`.
- **No CORS:** in development Vite proxies `/api`, in production the API serves the panel; keep both on
  the same origin.
- **Login limits** (`backend/app/core/limiter.py`): never count failed logins by e-mail alone — that
  lets anyone lock the owner out. Keep `LOGIN_FREE_FAILURES_PER_ACCOUNT` above what a single source can
  accumulate in an hour; `tests/test_bloqueio_login.py` enforces both sides.
- The WhatsApp message text exists in `web/src/features/work-orders/mensagens.ts` and in
  `mobile/lib/mensagens.dart`; each has a test with the literal sentence, so change both.
