"""Textual-based interactive TUI."""

from __future__ import annotations

import asyncio

from textual import on
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, Markdown, Static

from bashops_agent.agents.main import ask
from bashops_agent.config import Settings


class BashopsApp(App[None]):
    """Interactive chat UI for bashops-agent."""

    CSS = """
    #conversation {
        height: 1fr;
        border: tall $accent;
        padding: 1 2;
    }
    #status {
        height: 1;
        color: $text-muted;
    }
    Input { dock: bottom; }
    """
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear", "Clear"),
    ]

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.history: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield Markdown(
                "# bashops-agent\n\nAsk anything about your infrastructure.", id="conversation"
            )
            yield Static("Ready.", id="status")
        yield Input(placeholder="Type your question...")
        yield Footer()

    @on(Input.Submitted)
    async def on_submit(self, event: Input.Submitted) -> None:
        prompt = event.value.strip()
        if not prompt:
            return
        event.input.value = ""

        conv = self.query_one("#conversation", Markdown)
        status = self.query_one("#status", Static)

        self.history.append(f"**You:** {prompt}\n")
        await conv.update("\n".join(self.history))
        status.update("Thinking...")

        try:
            answer = await asyncio.wait_for(
                ask(prompt, self.settings),
                timeout=self.settings.llm.timeout_seconds,
            )
        except TimeoutError:
            answer = "LLM timed out. Try a simpler question."
        except Exception as e:
            answer = f"Error: {e}"

        self.history.append(f"**copilot:** {answer}\n")
        await conv.update("\n".join(self.history))
        status.update("Ready.")

    def action_clear(self) -> None:
        self.history.clear()
        self.run_worker(
            self.query_one("#conversation", Markdown).update("# bashops-agent\n\nReady.")
        )


def run_tui(settings: Settings) -> None:
    BashopsApp(settings).run()
