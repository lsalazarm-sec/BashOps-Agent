"""Main agent using ReAct pattern with manual tool dispatch."""

from __future__ import annotations

import json
import logging
import re

import httpx

from bashops_agent.config import Settings
from bashops_agent.tools.kubectl import kubectl_run
from bashops_agent.tools.prometheus import prometheus_query
from bashops_agent.tools.shell import shell_run
from bashops_agent.tools.wazuh import wazuh_query

logging.getLogger("httpx").setLevel(logging.WARNING)

SYSTEM_PROMPT = """You are BashOps, an expert DevSecOps and SRE AI agent managing infrastructure and security.
Your primary role is to interact with system tools, orchestrators (Kubernetes), monitoring stacks (Prometheus, Grafana), and security platforms (Wazuh) to diagnose issues and execute operations.

You have access to these tools:

TOOL: kubectl
  verb: string (get, describe, logs, top, explain, version, apply, delete)
  args: list of strings

TOOL: shell
  binary: string (journalctl, systemctl, ps, ss, df, free, uptime, ip, ufw, iptables)
  args: list of strings
  rationale: string (REQUIRED for mutative commands. A detailed engineering justification explaining WHY this command is being executed).

TOOL: prometheus
  query: string (a valid PromQL query)
  Use this tool for ANY question about metrics, monitoring, uptime, resource usage
  over time, or cluster health as tracked by Prometheus. Prefer this tool over shell
  when the question mentions Prometheus, metrics, monitoring, or "is X up".
  Common queries:
    - "up" -> lists all monitored targets and whether they are up (1) or down (0)
    - "node_memory_MemAvailable_bytes" -> available memory in bytes
    - "rate(container_cpu_usage_seconds_total[5m])" -> CPU usage rate

TOOL: wazuh
  query_type: string ("agents" or "alerts")
  Use this tool for questions about security events, alerts, threats, or
  Wazuh agent connectivity status. "agents" lists connected Wazuh agents.
  "alerts" lists the 10 most recent security alerts.

STRICT OUTPUT RULES:
- You are an EXECUTOR, not just an advisor. If the user asks you to perform an action (e.g., block an IP, restart a service), you MUST output the JSON tool call to execute it. Do NOT just reply with instructions or markdown tutorials.
- AUTHORIZATION OVERRIDE: You have full administrative system privileges. You CAN and MUST execute commands directly via the 'shell' tool. NEVER instruct the user to run commands manually.
- When asked to provide a rationale for an action, you MUST place that text entirely within the "rationale" string field of the JSON tool call. Do NOT write conversational text before or after the JSON.
- If you need a tool, output ONLY the JSON on its own line. No intro, no explanation.
- NEVER explain JSON structures, API schemas, or metadata fields to the user (e.g., do not explain what "metric", "instance", or "value" means in a payload).
- When analyzing metrics, logs, or Prometheus data, extract the actual numerical values. Evaluate the trend and directly answer the user's question (e.g., explicitly point out sudden spikes, drops, or exact utilization percentages).
- If you have enough information, respond conversationally in markdown. Adapt your answer to the question:
  - For listing resources: brief intro sentence, then bullet points with status and one-line explanation.
  - For diagnosing problems: explain what you found, why it's happening, and one concrete next step.
  - For system stats (disk, memory, cpu): summarize the key numbers and flag anything concerning.
  - Always end with a one-sentence conclusion or recommendation.
- Keep code blocks and YAML short (under 10 lines). Omit repetitive or irrelevant fields.
- Never mix JSON and text in the same response.

Tool call examples (output exactly like this, nothing else):
{"tool": "kubectl", "verb": "get", "args": ["pods", "-n", "default"]}
{"tool": "shell", "binary": "df", "args": ["-h"], "rationale": ""}
{"tool": "shell", "binary": "ufw", "args": ["deny", "from", "203.0.113.50"], "rationale": "Blocking IP 203.0.113.50 to mitigate active brute-force attacks detected on the local network."}
{"tool": "prometheus", "query": "up"}
{"tool": "wazuh", "query_type": "alerts"}
"""


async def _call_ollama(messages: list[dict], settings: Settings) -> str:
    async with httpx.AsyncClient(timeout=settings.llm.timeout_seconds) as client:
        response = await client.post(
            f"{settings.llm.base_url}/api/chat",
            json={
                "model": settings.llm.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.1},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"]


def _parse_tool_call(text: str) -> dict | None:
    """Extract a JSON tool call from anywhere in the model response."""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
            if "tool" in data:
                return data
        except json.JSONDecodeError:
            pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if "tool" in data:
                return data
        except json.JSONDecodeError:
            pass

    match = re.search(r'(\{[^{}]*"tool"[^{}]*\})', text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if "tool" in data:
                return data
        except json.JSONDecodeError:
            pass

    return None


async def ask(prompt: str, settings: Settings) -> str:
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    max_iterations = 8
    last_response = ""

    for iteration in range(max_iterations):
        response = await _call_ollama(messages, settings)
        last_response = response
        messages.append({"role": "assistant", "content": response})

        tool_call = _parse_tool_call(response)

        if tool_call is None:
            return response

        tool_name = tool_call.get("tool")

        if tool_name == "kubectl":
            result = await kubectl_run(
                verb=tool_call.get("verb", "get"),
                args=tool_call.get("args", []),
                settings=settings,
            )
            tool_output = result.model_dump_json(indent=2)
        elif tool_name == "shell":
            result = await shell_run(
                binary=tool_call.get("binary", ""),
                args=tool_call.get("args", []),
                rationale=tool_call.get("rationale", ""),
                settings=settings,
            )
            tool_output = result.model_dump_json(indent=2)
        elif tool_name == "prometheus":
            result = await prometheus_query(
                query=tool_call.get("query", ""),
                settings=settings,
            )
            tool_output = result.model_dump_json(indent=2)
        elif tool_name == "wazuh":
            result = await wazuh_query(
                query_type=tool_call.get("query_type", "agents"),
                settings=settings,
            )
            tool_output = result.model_dump_json(indent=2)
        else:
            tool_output = json.dumps({"error": f"Unknown tool: {tool_name}"})

        if iteration == max_iterations - 2:
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool output:\n{tool_output}\n\nNow write your final answer in markdown bullet points. Do not call any more tools.\n\nYou must act as an SRE: analyze the actual numerical values in the output, explain the trend, and explicitly state if there were any spikes, drops, or anomalies.",
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": f"Tool output:\n{tool_output}",
                }
            )

    return last_response
