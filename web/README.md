# Painel web — Kadosh Ops

React 18 + Vite + TypeScript + Tailwind v4. Consome a mesma API que o app Android (`/api/v1`).

- Desenvolvimento: `scripts\web.ps1` (http://localhost:5173, proxy de `/api` para o backend em :8000)
- Build: `scripts\web.ps1 -Build` → `web/dist`, servido pelo próprio backend em `/`
- Sessão: cookie HttpOnly; a API está na mesma origem, por isso **não há CORS** (regra do projeto)
- Fontes da marca via `@fontsource/*` (self-hosted — a CSP não abre para domínios externos)
- Dinheiro sempre em **centavos inteiros**; formatação em `src/lib/format.ts`
