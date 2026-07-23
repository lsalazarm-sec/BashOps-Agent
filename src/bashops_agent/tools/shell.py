"""Generic shell command runner with strict allowlist and mutative safeguards."""

from __future__ import annotations

import asyncio
import shutil
import time
from typing import Annotated

from pydantic import BaseModel, Field
from rich.console import Console
from rich.prompt import Confirm

from bashops_agent.audit import record
from bashops_agent.config import Settings

MAX_OUTPUT_CHARS = 8000
console = Console()


class ShellResult(BaseModel):
    command: str
    stdout: str
    stderr: str
    return_code: int
    truncated: bool = False


class ShellBlocked(BaseModel):
    reason: str
    attempted_command: str


async def shell_run(
    binary: Annotated[
        str, Field(description="Binary name e.g. 'journalctl' or 'ufw'. Must be authorized.")
    ],
    args: Annotated[list[str], Field(description="Arguments to pass to the binary.")],
    rationale: Annotated[
        str, Field(description="Detailed engineering justification for the command. Required for mutative actions.", default="")
    ],
    settings: Settings,
) -> ShellResult | ShellBlocked:
    """Run a safe allowlisted shell binary or an authorized mutative command."""
    cmd_str = f"{binary} " + " ".join(args)

    # 1. Determine the command classification
    is_read_only = binary in settings.safety.shell_allowed_cmds
    
    # Using getattr safely in case the Pydantic settings model isn't updated yet
    mutative_cmds = getattr(settings.safety, "shell_mutative_cmds", [])
    is_mutative = binary in mutative_cmds

    # 2. Block unknown binaries immediately
    if not is_read_only and not is_mutative:
        return ShellBlocked(
            reason=f"Binary '{binary}' is neither in the allowed nor mutative lists.",
            attempted_command=cmd_str,
        )

    # 3. Apply strict validation for mutative commands
    if is_mutative:
        if settings.safety.read_only:
            return ShellBlocked(
                reason="Execution Blocked: Agent is in read-only mode. Restart with --respond flag to allow changes.",
                attempted_command=cmd_str,
            )
        
        rationale_required = getattr(settings.safety, "rationale_required", True)
        if rationale_required and not rationale.strip():
            return ShellBlocked(
                reason="Execution Blocked: Mutative commands require a clear rationale parameter explaining the 'why'.",
                attempted_command=cmd_str,
            )

        require_confirmation = getattr(settings.safety, "require_confirmation", True)
        if require_confirmation:
            console.print("\n[bold yellow]⚠️  Action Authorization Required[/bold yellow]")
            console.print(f"[bold cyan]Proposed Command:[/bold cyan] {cmd_str}")
            console.print(f"[bold cyan]Rationale:[/bold cyan] {rationale}")
            
            authorized = Confirm.ask("[bold red]Do you authorize this execution?[/bold red]")
            if not authorized:
                return ShellBlocked(
                    reason="Action aborted by the administrator.",
                    attempted_command=cmd_str,
                )

    # 4. Check binary availability
    if not shutil.which(binary):
        return ShellBlocked(
            reason=f"Binary '{binary}' not found in PATH", attempted_command=cmd_str
        )

    # 5. Execute the command
    start = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        binary,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    duration_ms = (time.perf_counter() - start) * 1000

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    truncated = False

    if len(stdout) > MAX_OUTPUT_CHARS:
        stdout = stdout[:MAX_OUTPUT_CHARS] + "\n... [TRUNCATED]"
        truncated = True

    result = ShellResult(
        command=cmd_str,
        stdout=stdout,
        stderr=stderr,
        return_code=proc.returncode or 0,
        truncated=truncated,
    )
    
    # 6. Audit logging
    record(
        tool="shell",
        inputs={"binary": binary, "args": args, "rationale": rationale},
        outputs={"return_code": result.return_code},
        success=result.return_code == 0,
        duration_ms=duration_ms,
    )
    
    return result
