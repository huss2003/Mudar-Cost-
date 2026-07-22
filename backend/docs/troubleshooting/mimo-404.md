# MiMo / DeepSeek API — Error Troubleshooting Guide

Common error scenarios when connecting Auto Cost Engine to the MiMo (vision) or
DeepSeek (text) AI providers via the OpenCode Go platform.

---

## How connectivity is tested

Run the following to diagnose:

```bash
make verify-ai
# or equivalently:
python scripts/verify_ai_connectivity.py

# For full endpoint dumps:
python scripts/verify_ai_connectivity.py --verbose
```

The script probes two endpoints per provider:
- `GET  /v1/models`           — lightweight auth + connectivity
- `POST /v1/chat/completions` — actual inference path

---

## Error: `body='Not Found' not valid JSON`

**Symptom:** HTTP 200 with plain-text body `"Not Found"` instead of JSON.

```
MiMo         ❌ UNREACHABLE
             Error: body='Not Found' not valid JSON
```

**Cause:** The API base URL points to a server that doesn't serve the
OpenAI-compatible API directly. This typically happens when the endpoint
is set to a Cloudflare-protected gateway (e.g. `api.opencode.ai`) that
rejects unknown paths or routes them to a fallback page.

**Resolution:**

1. Verify the API base URL is correct:
   ```bash
   curl -v https://api.opencode.ai/v1/models
   # Should return JSON with model list; if it returns "Not Found",
   # the path isn't served at this host.
   ```

2. Install and start the OpenCode ACP (API Control Plane) server:
   ```bash
   # Install OpenCode CLI (if not already)
   opencode acp
   ```
   The ACP server exposes a local endpoint that the clients can reach.

3. Point clients to the local ACP endpoint:
   ```
   MIMO_API_BASE=http://localhost:PORT/v1
   DEEPSEEK_API_BASE=http://localhost:PORT/v1
   ```

---

## Error: `DNS NXDOMAIN`

**Symptom:**
```
Error: DNS NXDOMAIN for 'api.opencodego.com'
```

**Cause:** The config is using the old domain `api.opencodego.com` which no
longer resolves.

**Resolution:**

Update the environment variables to the current domain:

```bash
# Change this:
MIMO_API_BASE=https://api.opencodego.com/v1
DEEPSEEK_API_BASE=https://api.opencodego.com/v1

# To this:
MIMO_API_BASE=https://api.opencode.ai/v1
DEEPSEEK_API_BASE=https://api.opencode.ai/v1
```

Also check `app/ai/models.py` — the `provider` field for both model specs
may still say `"opencodego"` (cosmetic, doesn't affect connectivity).

---

## Error: `Connection refused / DNS failure`

**Symptom:**
```
Error: Connection refused / DNS failure
```

**Cause:** The ACP (API Control Plane) proxy server is not running. The
OpenCode platform requires a local ACP server to relay requests to the
actual inference endpoint.

**Resolution:**

```bash
# Start the ACP server
opencode acp

# If opencode isn't installed:
# 1. Download/install from https://opencode.ai
# 2. Authenticate via the TUI:  opencode → /connect
# 3. Start the proxy:            opencode acp
```

The ACP server prints a local URL (usually `http://localhost:PORT`).
Update your environment:

```
MIMO_API_BASE=http://localhost:PORT/v1
DEEPSEEK_API_BASE=http://localhost:PORT/v1
```

---

## Error: `HTTP 401 Unauthorized`

**Symptom:**
```
Error: HTTP 401 Unauthorized — API key rejected
```

**Cause:** The API key is expired, invalid, or doesn't match the expected
format for the configured base URL.

**Resolution:**

1. Re-authenticate at the OpenCode auth portal:
   ```
   https://opencode.ai/auth
   ```

2. Copy the new API key (starts with `sk-...`).

3. Update your `.env` or shell environment:
   ```bash
   MIMO_API_KEY=sk-your-new-key-here
   DEEPSEEK_API_KEY=sk-your-new-key-here
   ```

4. Verify the key is picked up:
   ```bash
   python scripts/verify_ai_connectivity.py --verbose
   ```

---

## Error: `Connection refused` when hitting the ACP server

**Symptom:**
```
Error: Connection refused / DNS failure: ...
```

**Cause:** The ACP server address/port in the config doesn't match the
actual running ACP server.

**Resolution:**

1. Check which port the ACP server is listening on:
   ```bash
   opencode acp
   # Look for output like "Listening on http://localhost:1234"
   ```

2. Align the API base in your `.env`:
   ```bash
   MIMO_API_BASE=http://localhost:1234/v1
   DEEPSEEK_API_BASE=http://localhost:1234/v1
   ```

---

## Both providers show `No API key configured`

**Symptom:**
```
MiMo         ❌ UNREACHABLE
             Error: No API key configured (set env var)
DeepSeek     ❌ UNREACHABLE
             Error: No API key configured (set env var)
```

**Cause:** Neither `MIMO_API_KEY` nor `DEEPSEEK_API_KEY` are set, and
the `.env` file has them blank.

**Resolution:**

1. Get an API key from https://opencode.ai/auth
2. Set both keys in `.env`:
   ```
   MIMO_API_KEY=sk-...
   DEEPSEEK_API_KEY=sk-...
   ```
3. Or export them in your shell session:
   ```bash
   export MIMO_API_KEY=sk-...
   export DEEPSEEK_API_KEY=sk-...
   ```

---

## Diagnostics cheatsheet

```bash
# Full connectivity check
make verify-ai

# Verbose output with raw responses
python scripts/verify_ai_connectivity.py --verbose

# Quick DNS check
nslookup api.opencode.ai

# Quick HTTP check (MiMo models endpoint)
curl -v https://api.opencode.ai/v1/models

# Quick HTTP check (chat completions)
curl -v -X POST https://api.opencode.ai/v1/chat/completions \
  -H "Authorization: Bearer $MIMO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"mimo-v2.5","messages":[{"role":"user","content":"ping"}],"max_tokens":5}'

# Check if ACP server is running
curl -v http://localhost:1234/v1/models
```

---

## Reading the connectivity report

The script writes a structured JSON report to
`/tmp/work/connectivity_report.json` (Linux/Mac) or
`%TEMP%\work\connectivity_report.json` (Windows).

```json
{
  "timestamp": "2026-07-22T12:34:56+00:00",
  "mimo": {
    "ok": false,
    "status_code": 200,
    "error": "body='Not Found' not valid JSON",
    "endpoints_tested": ["https://api.opencode.ai/v1/models", ...]
  },
  "deepseek": { ... },
  "conclusion": "API_ENDPOINT_UNREACHABLE",
  "remediation": "..."
}
```

Each run overwrites the report, so the file always reflects the last probe.
