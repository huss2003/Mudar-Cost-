"""
Prometheus metrics for Auto Cost Engine.

Naming convention
-----------------
- ``ace_<noun>_<suffix>`` where ``<suffix>`` follows Prometheus best
  practices (``_total`` for counters, ``_seconds`` for histograms).
- Labels are kept low-cardinality (at most a handful per metric).

Metrics defined
---------------
**Counters** (cumulative, never decrease)::

    ace_drawings_uploaded_total     {file_type, status}
    ace_objects_detected_total      {object_type}
    ace_boq_computed_total
    ace_ai_calls_total              {provider, model, outcome}
    ace_http_requests_total         {method, route, status}

**Histograms** (latency / duration distributions)::

    ace_cost_engine_duration_seconds
    ace_ai_latency_seconds          {provider}
    ace_parse_duration_seconds      {file_type}

**Gauges** (point-in-time values)::

    ace_active_projects
    ace_sse_connections
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# ------------------------------------------------------------------
# Counters
# ------------------------------------------------------------------

drawings_uploaded: Counter = Counter(
    "ace_drawings_uploaded_total",
    "Total drawings uploaded",
    ["file_type", "status"],
)

objects_detected: Counter = Counter(
    "ace_objects_detected_total",
    "Objects detected by type",
    ["object_type"],
)

boq_computed: Counter = Counter(
    "ace_boq_computed_total",
    "BOQ computations triggered",
)

ai_calls: Counter = Counter(
    "ace_ai_calls_total",
    "AI API calls",
    ["provider", "model", "outcome"],
)

http_requests: Counter = Counter(
    "ace_http_requests_total",
    "HTTP requests",
    ["method", "route", "status"],
)

# ------------------------------------------------------------------
# Histograms
# ------------------------------------------------------------------

cost_engine_duration: Histogram = Histogram(
    "ace_cost_engine_duration_seconds",
    "Cost engine computation duration",
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 5, 10],
)

ai_latency: Histogram = Histogram(
    "ace_ai_latency_seconds",
    "AI API call latency",
    ["provider"],
    buckets=[0.1, 0.5, 1, 2, 5, 10, 30],
)

parse_duration: Histogram = Histogram(
    "ace_parse_duration_seconds",
    "Drawing parse duration",
    ["file_type"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60],
)

# ------------------------------------------------------------------
# Gauges
# ------------------------------------------------------------------

active_projects: Gauge = Gauge(
    "ace_active_projects",
    "Projects currently being processed",
)

sse_connections: Gauge = Gauge(
    "ace_sse_connections",
    "Active SSE connections",
)
