# VeriteLex AI

Bench-side case analysis for DIFC Courts judges — chronology, issues, submissions, grounding and a multi-model council. Implemented from the Claude Design prototype `VeriteLexAI v3.dc.html`.

**Stack:** Next.js 16 (App Router, Turbopack) · React 19 · TypeScript · Tailwind CSS v4

```bash
npm install
npm run dev     # http://localhost:3000
npm run build   # production build
```

## Routes

| Path | Screen |
| --- | --- |
| `/login` | Sign-in and one-time code |
| `/cases` | Case list with search, scope and status filters |
| `/upload?step=1..3` | New case from documents (3-step wizard) |
| `/cases/[caseId]/[section]` | Case report — `background`, `matrix`, `mapping`, `issues`, `subs?issue=n`, `tools`, `gaps`, `council`, `ask`, `questions`, `docs` |
| `/settings/[tab]` | `connectors`, `council`, `policy` |

## Layout

- `src/lib/data.ts` — all demo content (the CFI-114/2026 report, models, connectors). Swap for API calls when a backend exists.
- `src/lib/store.tsx` — client state shared across pages: enabled models, connectors, grounding policy, the simulated new-case pipeline, toast, export dialog, bench-note pins.
- `src/components/` — screens; `report/` holds one component per report section; `ui.tsx` holds shared primitives.

## Prototype behaviour kept as-is

- Every "Open report" link opens the CFI-114/2026 report — it is the only report in the demo data.
- Model answers, council runs and the processing pipeline are simulated client-side.
- The dark "Prototype · Jump to" bar is rendered from `src/components/proto-nav.tsx`; remove it from `src/app/layout.tsx` for production.
# VeritelexAI
