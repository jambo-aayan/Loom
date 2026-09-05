# Loom frontend

Next.js (TypeScript/React) dashboard, installable as a PWA, consuming the FastAPI backend's REST
API. Visual design system (color tokens, Tiro Bangla/Space Grotesk/IBM Plex pairing, the 5-tab +
2-header-icon mobile nav pattern) is reused from `../design/HANDOVER.md`, `../design/canvas/`,
and `../design/prototype/loom-prototype.html` — see `tailwind.config.ts` for the token mapping.

## Local dev

```bash
cd frontend
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_API_BASE_URL, defaults to localhost:8000
npm run dev
```

Requires the backend running (`cd ../backend && uvicorn loom.api.main:app --port 8000`) — the
backend needs no external credentials for local dev either (see `../backend/README.md`).

```bash
npm run build   # production build; also type-checks and lints
npm run lint
npx tsc --noEmit
```

## Pages (App Router)

- `/` — Overview: cash + positions, "run trading pass" for on-demand demo runs.
- `/approvals` — pending-approval queue, per-signal Insight screening commentary, approve/reject
  with an optional note.
- `/strategies`, `/strategies/[id]` — strategy detail: live cumulative-return chart, trade log,
  config version changelog, and backtesting/promoting a draft parameter change.
- `/history` — every decided signal with its actual or counterfactual outcome and note.
- `/settings` — kill switch (demo), per-strategy live-enabled toggle.
- `/backtest`, `/insights` — light M1 placeholders; full builds are M2/M3 scope (tickets #37,
  #42).

## PWA

`public/manifest.json` + `public/sw.js` (registered from `components/RegisterServiceWorker.tsx`)
make the dashboard installable to the home screen on Android and iOS — the prerequisite for Web
Push on iOS specifically (ADR-0012). Web Push subscription/action buttons are M3 scope (tickets
#39-40).
