#!/usr/bin/env python3
"""
Auto Cost Engine — AI Provider Connectivity Tests (importable module)

Provides ``test_provider()`` and ``test_all_providers()`` which probe the
configured MiMo and DeepSeek endpoints and return structured results.

Usage (import)
--------------
    from scripts.connectivity_test import test_all_providers

    report = test_all_providers()
    print(report["conclusion"])
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin

import requests

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ProviderResult:
    """Outcome of probing a single provider's endpoint."""

    ok: bool = False
    status_code: int | None = None
    error: str = ""
    endpoints_tested: list[str] = field(default_factory=list)
    response_body_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConnectivityReport:
    """Full report from a connectivity probe."""

    timestamp: str = ""
    mimo: dict[str, Any] = field(default_factory=dict)
    deepseek: dict[str, Any] = field(default_factory=dict)
    conclusion: str = "PENDING"
    remediation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Endpoint probe helpers
# ---------------------------------------------------------------------------

_MIMO_ENDPOINTS = [
    "models",
    "chat/completions",
]

_DEEPSEEK_ENDPOINTS = [
    "models",
    "chat/completions",
]


def _probe_endpoint(
    base_url: str,
    path: str,
    api_key: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 15,
) -> tuple[int | None, str, str]:
    """Issue a single HTTP request to *base_url/path*.

    Returns
    -------
    (status_code_or_None, response_body_truncated, error_message)
    """
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        if method == "GET":
            resp = requests.get(url, headers=headers, timeout=timeout)
        else:
            resp = requests.post(url, headers=headers, json=payload or {}, timeout=timeout)

        status = resp.status_code
        body = resp.text[:500]

        # Check for non-JSON bodies on 2xx (common "Not Found" body trap)
        if 200 <= status < 300:
            try:
                resp.json()
            except (json.JSONDecodeError, ValueError):
                return status, body, f"body={body!r} not valid JSON"

        if status == 401:
            return status, body, f"HTTP 401 Unauthorized — API key rejected"
        if status == 404:
            # Could be the endpoint path is wrong
            return status, body, f"HTTP 404 — path {path!r} not found on server"

        resp.raise_for_status()
        return status, body, ""

    except requests.exceptions.ConnectionError as exc:
        return None, "", f"Connection refused / DNS failure: {exc}"
    except requests.exceptions.Timeout:
        return None, "", f"Request timed out after {timeout}s"
    except requests.exceptions.HTTPError as exc:
        st = exc.response.status_code if exc.response is not None else "?"
        bt = exc.response.text[:200] if exc.response is not None else ""
        return st, bt, f"HTTP {st}: {bt}"
    except requests.exceptions.RequestException as exc:
        return None, "", f"Request failed: {exc}"


def _check_dns_resolve(hostname: str) -> Optional[str]:
    """Quick DNS check. Returns error string or *None* on success."""
    import socket

    try:
        socket.getaddrinfo(hostname, 443)
        return None
    except socket.gaierror as exc:
        return f"DNS NXDOMAIN for {hostname!r}: {exc}"
    except Exception as exc:
        return f"DNS check error: {exc}"


def _extract_hostname(url: str) -> str:
    """Extract hostname from a URL string."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.hostname or url


# ---------------------------------------------------------------------------
# Public test functions
# ---------------------------------------------------------------------------


def test_provider(
    name: str,
    api_key: str,
    base_url: str,
    endpoints: list[str],
) -> ProviderResult:
    """Probe *endpoints* for a single provider.

    Parameters
    ----------
    name:
        Human label ("mimo" or "deepseek").
    api_key:
        Bearer token, may be empty.
    base_url:
        Base URL such as ``https://api.xiaomimimo.com/v1``.
    endpoints:
        Paths relative to *base_url* to probe (e.g. ``models``).

    Returns
    -------
    ProviderResult
    """
    result = ProviderResult()
    result.endpoints_tested = [f"{base_url.rstrip('/')}/{e}" for e in endpoints]

    # 0. Empty key check
    if not api_key:
        result.error = "No API key configured (set env var)"
        result.ok = False
        return result

    # 1. DNS check (first endpoint hostname)
    hostname = _extract_hostname(base_url)
    dns_err = _check_dns_resolve(hostname)
    if dns_err:
        result.error = dns_err
        result.ok = False
        return result

    # 2. Try GET /models (lightweight auth + connectivity check)
    for path in endpoints:
        method = "GET" if path == "models" else "POST"
        payload = (
            None
            if method == "GET"
            else {
                "model": name.replace("mimo", "mimo-v2.5").replace("deepseek", "deepseek-v4-flash"),
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            }
        )
        status, body, err = _probe_endpoint(base_url, path, api_key, method, payload)

        result.status_code = status
        result.response_body_preview = body

        if err:
            result.error = err
            result.ok = False
            # Keep probing other endpoints — surface the full picture
            continue

        # Success
        result.ok = True
        result.error = ""
        return result

    return result


def test_all_providers(
    mimo_api_key: str | None = None,
    mimo_base: str | None = None,
    deepseek_api_key: str | None = None,
    deepseek_base: str | None = None,
) -> ConnectivityReport:
    """Probe both MiMo and DeepSeek endpoints.

    Parameters
    ----------
    All arguments optional — values are read from environment when omitted.

    Returns
    -------
    ConnectivityReport
    """
    mimo_key = mimo_api_key or os.environ.get("MIMO_API_KEY", "")
    mimo_url = mimo_base or os.environ.get("MIMO_API_BASE", "https://api.xiaomimimo.com/v1")
    deepseek_key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY", "")
    deepseek_url = deepseek_base or os.environ.get(
        "DEEPSEEK_API_BASE", "https://api.opencode.ai/v1"
    )

    report = ConnectivityReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Test MiMo
    mimo_result = test_provider("mimo", mimo_key, mimo_url, _MIMO_ENDPOINTS)

    # Test DeepSeek
    deepseek_result = test_provider("deepseek", deepseek_key, deepseek_url, _DEEPSEEK_ENDPOINTS)

    report.mimo = mimo_result.to_dict()
    report.deepseek = deepseek_result.to_dict()

    # Derive conclusion
    all_ok = mimo_result.ok and deepseek_result.ok

    if mimo_result.ok and deepseek_result.ok:
        report.conclusion = "ALL_PROVIDERS_REACHABLE"
        report.remediation = ""
    elif not mimo_result.ok and not deepseek_result.ok:
        report.conclusion = "API_ENDPOINT_UNREACHABLE"
        report.remediation = _build_remediation(mimo_result, deepseek_result)
    elif not mimo_result.ok:
        report.conclusion = "MIMO_UNREACHABLE"
        report.remediation = _build_remediation(mimo_result, None)
    else:
        report.conclusion = "DEEPSEEK_UNREACHABLE"
        report.remediation = _build_remediation(None, deepseek_result)

    return report


def _build_remediation(
    mimo: ProviderResult | None,
    deepseek: ProviderResult | None,
) -> str:
    """Readable remediation advice based on the errors encountered."""
    steps: list[str] = [
        "═══════════════════════════════════════════════════════",
        "  AI CONNECTIVITY FAILED — REMEDIATION STEPS",
        "═══════════════════════════════════════════════════════",
    ]

    errors: dict[str, str] = {}
    if mimo and mimo.error:
        errors["MiMo"] = mimo.error
    if deepseek and deepseek.error:
        errors["DeepSeek"] = deepseek.error

    for provider, err in errors.items():
        steps.append(f"\n  [{provider}] {err}")
        if "DNS" in err or "NXDOMAIN" in err:
            steps.append(
                "    → DNS resolution failed. The hostname doesn't exist or isn't reachable."
            )
            steps.append("    → Check your MIMO_API_BASE / DEEPSEEK_API_BASE env vars.")
            steps.append("    → Example: https://api.xiaomimimo.com/v1 (MiMo) or opencode acp (DeepSeek)")
        if "Connection refused" in err:
            steps.append("    → The ACP (API proxy) server is not running.")
            steps.append("    → Start it with:  opencode acp")
            steps.append("    → Or in the OpenCode TUI: /connect → authenticate → opencode acp")
        if "401" in err:
            steps.append("    → API key is expired or invalid.")
            steps.append("    → Re-authenticate at https://mimo.mi.com (MiMo) or https://opencode.ai/auth (DeepSeek)")
            steps.append("    → Then update MIMO_API_KEY / DEEPSEEK_API_KEY in your .env")
        if "Not Found" in err or "404" in err:
            steps.append("    → The API path is wrong. Expected /v1/chat/completions or /v1/models.")
            steps.append("    → Verify MIMO_API_BASE / DEEPSEEK_API_BASE is correct.")
            steps.append("    → Try: curl -v https://api.xiaomimimo.com/v1/models")
        if "not valid JSON" in err:
            steps.append("    → The server returned a non-JSON response on a valid-looking path.")
            steps.append("    → This usually means the base URL points to a proxy/gateway")
            steps.append("      that doesn't serve the OpenAI-compatible API directly.")
            steps.append("    → Install the OpenCode CLI, run /connect, then start ACP server:")
            steps.append("         opencode acp")
            steps.append("    → The ACP server will expose a local endpoint compatible with clients.")

    steps.append(
        "\n  For full diagnostics, run:\n"
        "    python scripts/verify_ai_connectivity.py --verbose\n"
    )

    return "\n".join(steps)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
_DOT_ENV = os.path.join(PROJECT_ROOT, ".env")


def _dotenv_load() -> None:
    """Load **.env** if it exists (idempotent)."""
    if not os.path.isfile(_DOT_ENV):
        return
    with open(_DOT_ENV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            if key and not os.environ.get(key):
                os.environ.setdefault(key, val)


def main() -> int:
    """CLI entry point. Returns exit code (0 = all ok)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Verify AI provider connectivity (MiMo + DeepSeek)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print detailed endpoint responses",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write connectivity_report.json (default: /tmp/...)",
    )
    args = parser.parse_args()

    _dotenv_load()

    report = test_all_providers()

    # Determine output path
    output_path = args.output
    if not output_path:
        # Use a cross-platform temp location
        tmp_dir = "/tmp" if sys.platform != "win32" else os.environ.get("TEMP", "C:\\Temp")
        output_path = os.path.join(tmp_dir, "work", "connectivity_report.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
    print(f"Report written to {output_path}")

    # Print summary
    print()
    print("=" * 60)
    print("  AI PROVIDER CONNECTIVITY REPORT")
    print("=" * 60)
    print()
    print(f"  Timestamp : {report.timestamp}")
    print(f"  Conclusion: {report.conclusion}")
    print()

    for label, data in [("MiMo", report.mimo), ("DeepSeek", report.deepseek)]:
        status = "✅ REACHABLE" if data.get("ok") else "❌ UNREACHABLE"
        print(f"  {label:<12} {status}")
        if data.get("status_code"):
            print(f"              HTTP {data['status_code']}")
        if data.get("error"):
            print(f"              Error: {data['error']}")

    print()
    if report.remediation:
        print(report.remediation)

    if args.verbose:
        print()
        print("-" * 60)
        print("  RAW ENDPOINT RESPONSES")
        print("-" * 60)
        for label, data in [("MiMo", report.mimo), ("DeepSeek", report.deepseek)]:
            print(f"\n  [{label}]")
            print(f"    Endpoints tested: {', '.join(data.get('endpoints_tested', []))}")
            if data.get("response_body_preview"):
                print(f"    Response preview: {data['response_body_preview'][:300]}")

    print()
    if report.conclusion == "ALL_PROVIDERS_REACHABLE":
        print("  ✅  Both providers are reachable. The system is ready.")
        return 0
    else:
        print("  ❌  One or more providers are unreachable. See remediation above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
