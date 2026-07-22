# Supabase Edge Function — `api`

Single Supabase Edge Function that powers the entire backend. Mounted at `/functions/v1/api/*`.

## Prerequisites
1. Apply the schema once (run in Supabase dashboard → SQL editor):
   - `migrations/0001_init.sql`
2. Create two storage buckets (Storage → New bucket):
   - `drawings` (public read, used to feed MiMo vision calls with image URLs)
   - `exports` (public read, for downloadable BOQ files)
3. Set Edge Function secrets (`supabase functions secrets set KEY=value`):
   - `MIMO_API_KEY` — your OpenCode Go Premium MiMo v2.5 key (required for AI features)
   - `MIMO_BASE_URL` — default `https://api.xiaomimimo.com/v1` (override if OpenCode Go Premium uses a different base URL — verify before going live)
   - `MIMO_MODEL` — default `mimo-v2.5`

## Deploy

```bash
# Install Supabase CLI if not already
npm install -g supabase

# Link the CLI to this project (one-time)
supabase login
supabase link --project-ref pecnshwflkwpnwiskgmg

# Deploy the function
supabase functions deploy api --no-verify-jwt

# Set the MiMo secret (do this once after deploy)
supabase functions secrets set MIMO_API_KEY=your_opencode_go_premium_key
```

The `--no-verify-jwt` flag disables JWT verification so the Vercel proxy can call without forwarding user tokens. If you want auth, remove that flag and add a Bearer-check at the top of the router.

## Routes covered

| Frontend call | Edge Function route |
|---|---|
| `GET /healthz` | health check |
| `GET /projects` | list projects |
| `POST /projects` | create project |
| `GET /projects/:id` | get project |
| `GET /projects/:id/drawings` | list drawings for project |
| `POST /drawings` | create drawing record (status=uploaded) |
| `GET /drawings/:id/status` | status + objects_detected count |
| `GET /drawings/:id/objects` | detected_objects list (normalised for frontend) |
| `GET /drawings/types` | catalogue of object types |
| `POST /projects/:id/compute-quantities` | expand objects → BOQ items |
| `GET /projects/:id/boq` | grouped BOQ + summary |
| `GET /projects/:id/cost-summary` | trades + total |
| `POST /projects/:id/ai/ask` | MiMo chat over BOQ |
| `POST /projects/:id/ai/missing-boq` | MiMo missing-trades |
| `POST /projects/:id/ai/anomalies` | outlier flags |
| `POST /projects/:id/ai/value-engineering` | savings suggestions |
| `GET /ai/capabilities` | what's wired |
| `POST /projects/:id/proposal` | generate proposal CSV |
| `POST /projects/:id/export` | generate xlsx/pdf |
| `POST /projects/:id/purchase-list` | generate purchase list |
| `POST /projects/:id/client-presentation` | generate presentation |
| `GET /exports` | list exports |
| `GET /exports/:id/download` | signed URL for download |

## What's NOT covered yet (gaps to close)

- **PDF rasterisation.** Drawing upload expects a PNG in the `drawings` bucket; PDFs aren't auto-rasterised. Add a Cloud Function or Deno WASM pdf.js step before MiMo vision, or change the upload flow to client-side canvas render.
- **CAD/DWG parsing.** Same story — DWG/DXF aren't parsed. Frontend accepts `.dwg,.dxf,.pdf`; for the MVP, real PDFs/DWGs get uploaded as-is, but only PNGs trigger detection.
- **Real G.U.-calibrated geometric rules.** The current `BOQ_RULES` table in `api/index.ts` is a placeholder. Calibrate against the G.U. reference Excel (₹62,51,940) before claiming round-trip accuracy.
- **Auth.** No Bearer-token check. Anyone with the URL can hit it. Add `verify_jwt = true` in deployment + a token check at the router when ready.
- **SSE live updates.** Frontend wants `EventSource('/api/v1/projects/:id/live')`. Not implemented yet.

## Test locally

```bash
supabase functions serve api --no-verify-jwt --env-file ./supabase/.env.local
# → listens on http://localhost:54321/functions/v1/api/*
curl http://localhost:54321/functions/v1/api/healthz
```
