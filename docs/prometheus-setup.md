# Prometheus Setup Guide

`bashops-agent` integrates with Prometheus for metrics and observability queries.
This guide documents how Prometheus was deployed and how to access it.

## Architecture

Prometheus runs inside the `kind` cluster as part of the `kube-prometheus-stack`
Helm chart — not as a system service. This means `systemctl status prometheus`
will never find it; it lives as a pod in the `monitoring` namespace.

The full stack installed by `kube-prometheus-stack`:

| Component | Role |
|---|---|
| Prometheus | Metrics collection and storage (TSDB) |
| Grafana | Dashboard visualization |
| Alertmanager | Alert routing and grouping |
| kube-state-metrics | Kubernetes object state metrics |
| node-exporter | Host hardware metrics (CPU, RAM, disk, network) |

## Deployment

```bash
# Add the Helm repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

# Create the namespace
kubectl create namespace monitoring

# Install the stack
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set prometheus.prometheusSpec.resources.requests.memory=512Mi \
  --set prometheus.prometheusSpec.resources.limits.memory=1Gi
```

Verify all pods are running:

```bash
kubectl get pods -n monitoring
```

Expected output: alertmanager, grafana, prometheus-operator, kube-state-metrics,
prometheus, and node-exporter all in `Running` state.

## Accessing Prometheus

Prometheus does not have an external LoadBalancer or Ingress in this local setup.
Access it via `kubectl port-forward`:

```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
```

Keep this terminal running. Prometheus is now available at `http://localhost:9090`.

Verify with:

```bash
curl -s http://localhost:9090/api/v1/query?query=up | python3 -m json.tool | head -20
```

## Accessing Grafana

```bash
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
```

Open `http://localhost:3000` in your browser.

Default credentials:

```bash
# Username
admin

# Password (retrieve from the secret)
kubectl get secret -n monitoring prometheus-grafana \
  -o jsonpath="{.data.admin-password}" | base64 -d
```

## Grafana dashboards

The `kube-prometheus-stack` chart ships with pre-configured production-grade
dashboards. See [docs/grafana-dashboards.md](grafana-dashboards.md) for
screenshots and descriptions of each dashboard included.

Key dashboards available out of the box:

- **Kubernetes / Compute Resources / Cluster** — cluster-wide CPU and memory
- **Kubernetes / Compute Resources / Namespace (Pods)** — per-pod resource usage
- **Prometheus / Overview** — Prometheus internal health and query performance
- **Kubernetes / API server** — API server SLOs (99.996% availability)
- **Node Exporter / Nodes** — host hardware metrics

## The `prometheus` tool

`src/bashops_agent/tools/prometheus.py` executes PromQL queries against the
Prometheus HTTP API at `localhost:9090` and returns parsed results.

No authentication is required — Prometheus in this setup is read-only by design.

Example usage:

```bash
bashops ask "is everything up according to prometheus?"
bashops ask "what's the available memory according to prometheus?"
bashops ask "show me the CPU usage trend for the last hour"
```

## Note on control-plane metrics in kind

In local `kind` clusters, some control-plane components (`etcd`, `kube-scheduler`,
`kube-proxy`, `kube-controller-manager`) do not expose Prometheus metrics endpoints
by default. They appear as "down" in Prometheus target lists and in `bashops-agent`
responses — this is a `kind` limitation, not a real cluster health issue.

In a managed Kubernetes service (EKS, AKS, GKE) or a properly configured on-prem
cluster, these targets are reachable.

## Troubleshooting

**Port-forward must be active for the tool to work**
The `prometheus` tool queries `localhost:9090`. If the port-forward tunnel is
closed (e.g. the terminal running it was closed or the session expired), the agent
will report Prometheus as unreachable or "not installed". This is the most common
issue. Reopen the tunnel:

```bash
kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090
```

**Prometheus pods not starting**
If pods are in `Pending` or `CrashLoopBackOff`, check available resources:

```bash
kubectl describe pod -n monitoring <pod-name>
kubectl top nodes
```

The `kube-prometheus-stack` is resource-intensive for a local cluster. If your
machine has less than 8GB RAM available, reduce memory limits in the Helm install
command.

**Helm repository signature error**
If `helm repo add` fails with a GPG signature error from `baltocdn.com`, use the
official install script instead:

```bash
curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3
chmod +x get_helm.sh
./get_helm.sh
```
