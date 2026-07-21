"""Wazuh tool: agent status via the Manager API, alerts via the Indexer API.

Wazuh splits data across two separate services:
  - Manager API (port 55000, JWT auth) -> agents, manager config
  - Indexer API (port 9200, basic auth) -> alerts (OpenSearch-backed)

Safety: read-only by design. Only GET/_search style queries are implemented.
"""

from __future__ import annotations

import time
from typing import Annotated, Literal

import httpx
from pydantic import BaseModel, Field

from infra_copilot.audit import record
from infra_copilot.config import Settings


class WazuhResult(BaseModel):
    query_type: str
    results: list[dict]


class WazuhError(BaseModel):
    query_type: str
    error: str


async def _get_manager_token(base_url: str, username: str, password: str) -> str:
    """Authenticate against the Wazuh Manager API and return a JWT token."""
    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        response = await client.post(
            f"{base_url}/security/user/authenticate",
            auth=(username, password),
        )
        response.raise_for_status()
        return response.json()["data"]["token"]


async def _query_agents(settings: Settings) -> list[dict]:
    """List Wazuh agents and their connection status via the Manager API."""
    base_url = getattr(settings, "wazuh_manager_url", "https://localhost:55000")
    username = getattr(settings, "wazuh_user", "wazuh-wui")
    password = getattr(settings, "wazuh_password", "")

    token = await _get_manager_token(base_url, username, password)
    headers = {"Authorization": f"Bearer {token}"}

    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        response = await client.get(f"{base_url}/agents", headers=headers)
        response.raise_for_status()
        data = response.json()

    return data.get("data", {}).get("affected_items", [])


async def _query_alerts(settings: Settings) -> list[dict]:
    """Fetch the most recent security alerts via the Indexer API (OpenSearch)."""
    indexer_url = getattr(settings, "wazuh_indexer_url", "https://localhost:9200")
    indexer_user = getattr(settings, "wazuh_indexer_user", "admin")
    indexer_password = getattr(settings, "wazuh_indexer_password", "")

    query = {
        "size": 10,
        "sort": [{"timestamp": {"order": "desc"}}],
        "_source": ["timestamp", "agent.name", "rule.description", "rule.level", "rule.mitre"],
    }

    async with httpx.AsyncClient(verify=False, timeout=15) as client:
        response = await client.post(
            f"{indexer_url}/wazuh-alerts-*/_search",
            json=query,
            auth=(indexer_user, indexer_password),
        )
        response.raise_for_status()
        data = response.json()

    hits = data.get("hits", {}).get("hits", [])
    return [hit.get("_source", {}) for hit in hits]


async def wazuh_query(
    query_type: Annotated[
        Literal["agents", "alerts"],
        Field(
            description=(
                "'agents' lists connected Wazuh agents and their status. "
                "'alerts' lists the 10 most recent security alerts, sorted newest first."
            )
        ),
    ],
    settings: Settings,
) -> WazuhResult | WazuhError:
    """Query Wazuh for agent status or recent security alerts.

    Examples:
        wazuh_query(query_type="agents")
        wazuh_query(query_type="alerts")
    """
    start = time.perf_counter()
    try:
        if query_type == "agents":
            items = await _query_agents(settings)
        else:
            items = await _query_alerts(settings)

        duration_ms = (time.perf_counter() - start) * 1000
        result = WazuhResult(query_type=query_type, results=items)
        record(
            tool="wazuh",
            inputs={"query_type": query_type},
            outputs={"result_count": len(items)},
            success=True,
            duration_ms=duration_ms,
        )
        return result

    except httpx.HTTPError as e:
        duration_ms = (time.perf_counter() - start) * 1000
        error = WazuhError(query_type=query_type, error=f"Wazuh API error: {e}")
        record(
            tool="wazuh",
            inputs={"query_type": query_type},
            outputs=error.model_dump(),
            success=False,
            duration_ms=duration_ms,
        )
        return error
