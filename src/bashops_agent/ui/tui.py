import subprocess

from rich.markdown import Markdown
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, RichLog


class BashopsApp(App):
    CSS_PATH = "bashops.tcss"
    TITLE = "🤖 BashOps-Agent"
    SUB_TITLE = "Local LLM Infrastructure agent for DevSecOps"

    def __init__(self, settings) -> None:
        super().__init__()
        self.settings = settings

        # 1. Counter to track the number of queries
        self.query_counter = 0

        # 2. List of generic, professional thinking messages
        self.thinking_messages = [
            "[dim italic]Processing query and retrieving system context...[/dim italic]",
            "[dim italic]Executing reasoning loop and tool dispatch...[/dim italic]",
            "[dim italic]Analyzing requested data and formatting output...[/dim italic]",
            "[dim italic]Synthesizing operational parameters...[/dim italic]",
        ]

    def compose(self) -> ComposeResult:
        """Define the layout with a single, clean chat log."""
        yield Header()

        with Vertical(id="chat-container"):
            yield RichLog(id="chat-log", highlight=True, markup=True)

        yield Input(id="user-input", placeholder="Ask your infrastructure questions here...")
        yield Footer()

    def on_mount(self) -> None:
        """Executes once the UI is successfully rendered on screen."""
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write(
            "[bold cyan]System:[/bold cyan] BashOps Agent Online --> What are we investigating today Luis?"
        )

    @work(exclusive=True, thread=True)
    def process_query(self, query: str) -> None:
        """Runs the LLM agent via subprocess to guarantee zero import/syntax errors."""
        try:
            result = subprocess.run(
                ["uv", "run", "bashops", "ask", query], capture_output=True, text=True, check=True
            )
            response = result.stdout.strip()
            self.call_from_thread(self.update_chat_log, response)

        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else str(e)
            self.call_from_thread(
                self.update_chat_log, f"[bold red]Execution Error:[/bold red]\n{error_output}"
            )
        except Exception as e:
            self.call_from_thread(self.update_chat_log, f"[bold red]System Error:[/bold red] {e!s}")

    def update_chat_log(self, message: str) -> None:
        """Safely updates the UI from a background thread with rich Markdown rendering."""
        chat_log = self.query_one("#chat-log", RichLog)
        chat_log.write("\n[bold blue]BashOps:[/bold blue]")
        chat_log.write(Markdown(message))
        chat_log.write("\n")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Captures input text, cycles the thinking message, and runs the query."""
        chat_log = self.query_one("#chat-log", RichLog)
        user_query = event.input.value

        if not user_query.strip():
            return

        # Write user query and clear input
        chat_log.write(f"\n[bold green]You:[/bold green] {user_query}")
        event.input.clear()

        # 3. Select the next thinking message using modulo math
        # This guarantees it loops: 0, 1, 2, 3, 0, 1, 2, 3...
        message_index = self.query_counter % len(self.thinking_messages)
        selected_message = self.thinking_messages[message_index]

        # Write the selected dynamic message
        chat_log.write(selected_message)

        # 4. Increment the counter for the next time
        self.query_counter += 1

        # Launch the background worker
        self.process_query(user_query)


def run_tui(settings) -> None:
    app = BashopsApp(settings=settings)
    app.run()
