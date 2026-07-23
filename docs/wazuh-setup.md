# Wazuh Integration Guide | bashops-agent

The `bashops-agent` integrates with Wazuh to provide real-time security agent status and alert querying directly from the command line. 

This guide documents how the Wazuh infrastructure is deployed and how the LLM agent interacts with its APIs.

<!--Login -->
![Wazuh Login Screen](wazuh/wazuh-login-screen.png)

<!-- Overview -->
![Wazuh Dashboard Overview](wazuh/wazuh-overview-page.png)

## Architecture

Wazuh runs independently of `bashops-agent` as a separate Docker Compose stack. The agent acts exclusively as a consumer of the Wazuh APIs, not the owner of the deployment.

Wazuh splits data access across two distinct services requiring different authentication methods:

| Service | Port | Auth Mechanism | Primary Use Case |
|---|---|---|---|
| **Manager API** | 55000 | JWT token (user/pass login) | Querying Agent status & OS info |
| **Indexer API (OpenSearch)** | 9200 | Basic Auth | Querying Security alerts & logs |

## Deployment Strategy

Wazuh (Manager + Indexer + Dashboard) is deployed via the official [`wazuh-docker`](https://github.com/wazuh/wazuh-docker) repository. To maintain Infrastructure as Code (IaC) principles, the deployment is automated using an Ansible playbook located at `ansible/deploy-wazuh.yml`.

```bash
cd ansible
ansible-playbook deploy-wazuh.yml -i inventory.ini
```

<!-- Ansible Playbook -->

![Ansible Playbook Execution](wazuh/ansible-playbook-deploy.png)

The playbook is idempotent: it clones the repository, generates necessary SSL certificates, and spins up the Docker Compose stack only if it isn't already running. It includes a health-check step that polls the Manager API until it responds before reporting success.

### Manual Steps (Automated by Ansible)
For reference, the playbook automates the following commands:
```bash
git clone https://github.com/wazuh/wazuh-docker.git -b v4.14.6 --single-branch
cd wazuh-docker/single-node
docker compose -f generate-indexer-certs.yml run --rm generator
docker compose up -d
```

## Connecting Security Agents

Any machine on the shared network can run the Wazuh agent and report back to the Manager. 

```bash
# Download and install the agent
curl -s -o wazuh-agent.deb https://packages.wazuh.com/4.x/apt/pool/main/w/wazuh-agent/wazuh-agent_4.14.6-1_amd64.deb
sudo WAZUH_MANAGER='<manager-ip>' dpkg -i ./wazuh-agent.deb

# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable wazuh-agent
sudo systemctl start wazuh-agent
```

<!-- Agent Deploy -->

![Wazuh Agent Deployment](wazuh/wazuh-agent-deploy.png)

To verify connected agents directly from the manager container:
```bash
docker exec -it single-node-wazuh.manager-1 /var/ossec/bin/agent_control -l
```

*Note: In the current development environment, two agents are actively monitored: the primary host (Ubuntu 24.04) and an isolated Kali Linux machine used for threat simulation and detection engineering.*

<!-- Active Agents -->
![Active Wazuh Agents](wazuh/active-agents.png)

## Tool Implementation: `wazuh.py`

The script `src/bashops_agent/tools/wazuh.py` exposes two read-only capabilities to the LLM:

*   **`agents`**: Authenticates against the Manager API to list connected endpoints, returning their status (active/disconnected), OS details, and agent version.
*   **`alerts`**: Queries the Indexer API targeting the `wazuh-alerts-*` index via OpenSearch `_search`. It sorts by timestamp and returns the 10 most recent security events, including rule descriptions, severity levels, and MITRE ATT&CK mapping.

**Example LLM Prompts:**
```bash
bashops ask "how many wazuh agents are currently connected?"
bashops ask "what are the most critical recent security alerts in Wazuh?"
```

## Configuration & Secrets Management

To configure the LLM agent, you need to extract the credentials generated during the Wazuh deployment.

**Extracting Indexer Credentials:**

<!-- Indexer Credentials -->
![Wazuh Indexer Credentials](wazuh/wazuh-credencials.png)

**Extracting Manager API Credentials:**

<!-- API Credentials -->
![Wazuh API Credentials](wazuh/API-credentials.png)

Wazuh connection settings are defined in the `Settings` class (`src/bashops_agent/config.py`):

```yaml
wazuh_manager_url: "https://localhost:55000"
wazuh_user: "wazuh-wui"
wazuh_indexer_url: "https://localhost:9200"
wazuh_indexer_user: "admin"
```

> ⚠️ **Security Notice:** For local development, credentials can be set in `config.py`. However, for production or shared environments, passwords and API tokens MUST be sourced from a `.env` file or a dedicated secrets manager. Hardcoding credentials in source control is strictly prohibited in this project.

## Troubleshooting

### Self-Signed Certificate Errors
Because this deployment relies on the `wazuh-docker` generation script, both the Manager and Indexer APIs use self-signed certificates. 

The `wazuh.py` tool intentionally disables certificate verification (`verify=False` in Python `requests`) to allow local testing. If migrating to a production Wazuh instance with valid CA-signed certificates, ensure this flag is set back to `True` to prevent Man-in-the-Middle (MitM) vulnerabilities.
