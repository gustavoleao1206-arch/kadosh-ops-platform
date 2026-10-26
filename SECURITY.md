# Security policy

Kadosh Ops runs a real business: its production database holds the shop's customers (names, phone
numbers, license plates) and its payments. Security reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report it privately through GitHub: open the **Security** tab of this repository and click
**Report a vulnerability** (GitHub's *Private vulnerability reporting*). Only the maintainer sees the
report.

Please include:

- the affected file, route or screen;
- steps to reproduce, or a proof of concept against a **local** instance;
- the impact you expect (access to another user's data, privilege escalation from `staff` to `admin`,
  session theft, money recorded or reversed without authorization, denial of service…).

You can expect an acknowledgement within a few days. Fixes land in the main codebase first and reach
this repository with the next public snapshot.

## Scope and rules

- **Test only against your own local instance** (see the README for how to run it). Never run scanners,
  brute force or exploits against the hosted service: it is the shop's production system, not a test
  environment.
- Use the demo data from `python -m app.cli seed-demo`. Do not access, modify or keep data that isn't
  yours.
- In scope: everything in this repository — the FastAPI backend (authentication, sessions, login
  throttling, CSRF protection, role checks, idempotency of payments and intake), the React panel and its
  Content Security Policy, the Flutter app (token storage, backup rules), the Dockerfile, `render.yaml`
  and the CI workflow.
- Out of scope: the hosting provider's own infrastructure, WhatsApp, and findings that require an
  already compromised server or administrator account.

## Supported versions

Only the latest snapshot on the default branch is supported.
