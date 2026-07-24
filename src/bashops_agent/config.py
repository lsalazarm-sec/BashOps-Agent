"""Configuration loaded from ~/.config/bashops-agent/config.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

CONFIG_DIR = Path.home() / ".config" / "bashops-agent"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DATA_DIR = Path.home() / ".local" / "share" / "bashops-agent"
AUDIT_LOG = DATA_DIR / "audit.jsonl"


class LLMConfig(BaseModel):
    provider: Literal["ollama"] = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "qwen2.5-coder:14b"
    temperature: float = 0.2
    max_tokens: int = 2048
    timeout_seconds: int = 120


class SafetyConfig(BaseModel):
    read_only: bool = True
    require_confirmation: bool = True
    audit_log: bool = True
    rationale_required: bool = True

    kubectl_allowed_verbs: list[str] = Field(
        default_factory=lambda: ["get", "describe", "logs", "top", "explain", "version"]
    )

    kubectl_mutative_verbs: list[str] = Field(
        default_factory=lambda: ["rollout", "scale", "delete", "apply", "cordon", "uncordon"]
    )

    shell_allowed_cmds: list[str] = Field(
        default_factory=lambda: [
            "journalctl",
            "systemctl",
            "ps",
            "ss",
            "df",
            "free",
            "uptime",
            "ip",
        ]
    )

    shell_mutative_cmds: list[str] = Field(
        default_factory=lambda: ["systemctl restart", "systemctl stop", "ufw", "iptables", "kill"]
    )


class Settings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    kubeconfig: str | None = None
    prometheus_url: str = "http://localhost:9090"
    wazuh_manager_url: str = "https://localhost:55000"
    wazuh_user: str = "wazuh-wui"
    wazuh_password: str = "MyS3cr37P450r.*-"
    wazuh_indexer_url: str = "https://localhost:9200"
    wazuh_indexer_user: str = "admin"
    wazuh_indexer_password: str = "SecretPassword"

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        path = path or CONFIG_FILE
        if not path.exists():
            return cls()
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    def save(self, path: Path | None = None) -> None:
        path = path or CONFIG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(self.model_dump(), f, default_flow_style=False)
