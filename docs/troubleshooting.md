# Troubleshooting

Common issues encountered during development and how they were resolved.

## LLM and Agent

**Agent returns JSON tool call instead of executing it**
This was the original issue that led to replacing PydanticAI with a manual ReAct
loop. Ollama's OpenAI-compatible `/v1/chat/completions` endpoint does not reliably
execute tool calls for all models — `qwen2.5-coder:14b` returns the tool call JSON
as plain text in the response body instead of in the `tool_calls` field.

Resolution: replaced PydanticAI tool calling with a manual ReAct loop that parses
JSON tool calls from the model's text response directly. See
[docs/architecture.md](architecture.md) for full details.

**Agent gives empty response or stops mid-conversation**
The model occasionally decides not to call any tool and returns an empty or minimal
response. This is a model behavior issue, not a code bug. Rephrase the question
more specifically, or restart the conversation.

**Responses take a long time**
Expected behavior for a 14B parameter model on a consumer GPU. Each question may
trigger multiple LLM inference passes (one per tool call + one for the final
answer). On an AMD RX 7700 XT with ROCm, typical response time is 15-30 seconds
per question. Use `qwen2.5-coder:7b` for faster responses at some cost to accuracy.

---

## Prometheus

**"Prometheus is not installed" but pods are running**
Prometheus runs inside the `kind` cluster as a pod — not as a system service.
`systemctl status prometheus` will never find it. The tool queries `localhost:9090`
via a `kubectl port-forward` tunnel. If that tunnel is closed, the tool cannot
reach Prometheus and reports it as unavailable.

Reopen the tunnel:
```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
```

**Control-plane components show as "down" in Prometheus**
`etcd`, `kube-scheduler`, `kube-proxy`, and `kube-controller-manager` do not expose
metrics endpoints in local `kind` clusters by default. This is a `kind` limitation —
not a real cluster health issue.

---

## Wazuh

**Wazuh agent not appearing in the manager**
Verify the agent service is running:
```bash
sudo systemctl status wazuh-agent
```

Check that the manager IP is reachable from the agent machine:
```bash
nc -zv <manager-ip> 1514
```

If the port is not open, check Docker is exposing it on `0.0.0.0` (not `127.0.0.1`):
```bash
docker compose -f ~/projects/wazuh-docker/single-node/docker-compose.yml ps
```

**`/alerts` endpoint returns 404 on port 55000**
Security alerts are not served by the Manager REST API. They live in the Indexer
(OpenSearch) on port 9200. The `wazuh.py` tool correctly queries each service on
its respective port. If you get a 404 querying alerts, verify the indexer is
running:
```bash
curl -k -u admin:SecretPassword "https://localhost:9200/_cat/indices/wazuh-alerts-*?v"
```

**Self-signed certificate warnings**
Both Wazuh APIs (Manager and Indexer) use self-signed certificates in this local
deployment. The tool sets `verify=False` for local development. This is a known
limitation — do not use against a production instance without proper certificates.

---

## Git and CI

**`ruff format --check` failing in CI but passing locally**
Run `uv run ruff format .` locally and commit the result. The CI checks formatting
strictly — if a file was edited manually (e.g. via `nano`), ruff's formatting may
differ from what was written by hand.

**`git pull --rebase` fails with "rebase already in progress"**
A previous rebase was interrupted. Resolve with:
```bash
git rebase --continue  # if working tree is clean
# or
git rebase --abort     # to cancel and start fresh
```

**Merge conflict markers in README**
If `<<<<<<< HEAD`, `=======`, `>>>>>>>` appear literally in the rendered README on
GitHub, the conflict was committed unresolved. Find and fix all markers:
```bash
grep -n "<<<<<<<\|=======\|>>>>>>>" README.md
```
Edit the file to keep only the correct version, then commit.

**TabError in Python files**
Mixing tabs and spaces in Python causes `TabError`. Fix with:
```bash
expand -t 4 src/bashops_agent/agents/main.py > /tmp/fixed.py
mv /tmp/fixed.py src/bashops_agent/agents/main.py
```

---

## ROCm and GPU

**PyTorch reports `GPU available: False` after ROCm install**
The `render` and `video` groups were added to your user but the change hasn't
applied to the current session. Run:
```bash
newgrp render
```
Or log out and back in.

**Ollama not using the GPU**
Verify ROCm sees the GPU:
```bash
rocminfo | grep -A 5 "Device Type.*GPU"
rocm-smi
```

If the GPU is visible but Ollama still runs on CPU, reinstall Ollama after ROCm
is confirmed working — the installer detects ROCm at install time.
