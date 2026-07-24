# 📚 BashOps Prompt Cheatsheet

This cheatsheet provides examples of effective prompts to get the most out of BashOps Agent across different infrastructure domains.

## 🐧 System & OS Diagnostics
* "What is eating my RAM right now? Show me the top 5 processes."
* "Check the disk space on the root partition. Is it critically full?"
* "Are there any failed systemd services?"
* "Show me the active network connections on port 80 and 443."
* "What is the current system uptime and load average?"

## 🐳 Docker & Containers
* "Is the docker service healthy and running?"
* "List all running containers and their resource usage."
* "Show me the last 50 lines of logs for the 'nginx' container."
* "Are there any exited containers that I should clean up?"

## ☸️ Kubernetes (K8s) Orchestration
* "Are all pods in the kube-system namespace running fine?"
* "Find any pods continuously restarting (CrashLoopBackOff) in the default namespace."
* "Check the events in the monitoring namespace for any recent warnings or errors."
* "Describe the node resource limits and current usage."
* "What is the status of the ingress controller?"

## 📈 Observability (Prometheus)
* "Are all prometheus targets currently up?"
* "What is the CPU usage trend for the last 30 minutes according to prometheus?"
* "Show me the available memory across all nodes via PromQL."
* "Are there any active alerts firing in Alertmanager?"

## 🛡️ Security & Wazuh SIEM
* "What are the most critical recent security alerts in wazuh?"
* "Are all Wazuh agents currently connected and active?"
* "Show me any failed SSH login attempts recorded recently."
* "Summarize the security events with severity level 12 or higher."

---
**💡 Pro Tip:** You can chain these! Try asking: *"Check if the database pod is running, and if it is, show me its RAM usage."*
