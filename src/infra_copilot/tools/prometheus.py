"""Prometheus PromQL query tool.

Talks to the Prometheus HTTP API directly (no extra dependencies needed).
Safety: read-only by design — PromQL has no way to mutate state, so no
allowlist is needed here, unlike kubectl and shell.
"""

from __future__ import annotations

import time
from typing import Annotated

import httpx
from pydantic import BaseModel, Field

from infra_copilot.audit import record
from infra_copilot.config import Settings


class PrometheusResult(BaseModel):
    query: str
    result_type: str
    results: list[dict]


class PrometheusError(BaseModel):
    query: str
    error: str


async def prometheus_query(
    query: Annotated[
        str,
        Field(
            description="A valid PromQL query, e.g. 'up' or 'rate(container_cpu_usage_seconds_total[5m])'"
        ),
    ],
    settings: Settings,
) -> PrometheusResult | PrometheusError:
    """Run a PromQL query against Prometheus and return the parsed result.

    Examples:
        prometheus_query(query="up")
        prometheus_query(query="sum(rate(container_cpu_usage_seconds_total[5m])) by (pod)")
        prometheus_query(query="node_memory_MemAvailable_bytes")
    """
    start = time.perf_counter()
    base_url = getattr(settings, "prometheus_url", "http://localhost:9090")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{base_url}/api/v1/query",
                params={"query": query},
            )
            response.raise_for_status()
            data = response.json()

        duration_ms = (time.perf_counter() - start) * 1000

        if data.get("status") != "success":
            error = PrometheusError(query=query, error=str(data))
            record(
                tool="prometheus",
                inputs={"query": query},
                outputs=error.model_dump(),
                success=False,
                duration_ms=duration_ms,
            )
            return error

        result_type = data["data"]["resultType"]
        results = data["data"]["result"]

        result = PrometheusResult(query=query, result_type=result_type, results=results)
        record(
            tool="prometheus",
            inputs={"query": query},
            outputs={"result_count": len(results)},
            success=True,
            duration_ms=duration_ms,
        )
        return result

    except httpx.HTTPError as e:
        duration_ms = (time.perf_counter() - start) * 1000
        error = PrometheusError(query=query, error=f"Connection failed: {e}")
        record(
            tool="prometheus",
            inputs={"query": query},
            outputs=error.model_dump(),
            success=False,
            duration_ms=duration_ms,
        )
        return error
