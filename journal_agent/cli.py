"""
CLI for journal-agent.

Commands
--------
prompt          Show today's personalized writing prompt.
write           Interactively write today's journal entry.
reflect --week  Generate a weekly reflection summary.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.style import Style
from rich.text import Text

from .agent import JournalAgent

console = Console()

DEFAULT_JOURNAL_DIR = str(Path("~/journal").expanduser())


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option(
    "--journal-dir",
    default=DEFAULT_JOURNAL_DIR,
    envvar="JOURNAL_DIR",
    show_default=True,
    help="Directory where journal entries are stored.",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    envvar="JOURNAL_MODEL",
    show_default=True,
    help="Claude model to use.",
)
@click.pass_context
def cli(ctx: click.Context, journal_dir: str, model: str) -> None:
    """Journal Agent — AI-powered personal journaling."""
    ctx.ensure_object(dict)
    ctx.obj["journal_dir"] = journal_dir
    ctx.obj["model"] = model


# ---------------------------------------------------------------------------
# prompt command
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def prompt(ctx: click.Context) -> None:
    """Show today's personalized writing prompt."""
    journal_dir = ctx.obj["journal_dir"]
    model = ctx.obj["model"]

    _ensure_api_key()

    agent = JournalAgent(journal_dir=journal_dir, model=model)

    console.print()
    with console.status("[bold green]Generating your daily prompt...[/]", spinner="dots"):
        daily_prompt = agent.generate_daily_prompt()

    console.print(
        Panel(
            Text(daily_prompt, style="italic"),
            title="[bold cyan]Today's Journal Prompt[/]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# write command
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--no-prompt",
    is_flag=True,
    default=False,
    help="Skip showing the daily prompt before writing.",
)
@click.pass_context
def write(ctx: click.Context, no_prompt: bool) -> None:
    """Write today's journal entry (with mood + theme tagging)."""
    journal_dir = ctx.obj["journal_dir"]
    model = ctx.obj["model"]

    _ensure_api_key()

    agent = JournalAgent(journal_dir=journal_dir, model=model)

    # --- optionally show the daily prompt first ---
    if not no_prompt:
        console.print()
        with console.status("[bold green]Fetching today's prompt...[/]", spinner="dots"):
            daily_prompt = agent.generate_daily_prompt()
        console.print(
            Panel(
                Text(daily_prompt, style="italic"),
                title="[bold cyan]Today's Prompt[/]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    # --- collect the entry ---
    console.print()
    console.print(Rule("[bold]Write your entry below[/] (blank line + Ctrl-D or Ctrl-Z to finish)"))
    console.print()

    lines: list[str] = []
    try:
        while True:
            line = input()
            lines.append(line)
    except EOFError:
        pass

    entry_text = "\n".join(lines).strip()

    if not entry_text:
        console.print("[yellow]No entry text — nothing saved.[/]")
        sys.exit(0)

    console.print()

    # --- process and save ---
    with console.status("[bold green]Analysing and saving your entry...[/]", spinner="dots"):
        result = agent.process_entry(entry_text, save=True)

    mood = result.get("mood", "unknown")
    themes: list[str] = result.get("themes") or []
    summary: str = result.get("summary", "")
    saved_path: str | None = result.get("saved_path")

    console.print()
    console.print(Panel(
        _build_analysis_renderable(mood, themes, summary),
        title="[bold green]Entry Analysis[/]",
        border_style="green",
        padding=(1, 2),
    ))

    if saved_path:
        console.print(f"[dim]Saved → {saved_path}[/dim]")
    console.print()


# ---------------------------------------------------------------------------
# reflect command
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--week",
    "period",
    flag_value="week",
    default=True,
    help="Generate a weekly reflection (default).",
)
@click.pass_context
def reflect(ctx: click.Context, period: str) -> None:
    """Generate a reflection summary from recent journal entries."""
    journal_dir = ctx.obj["journal_dir"]
    model = ctx.obj["model"]

    _ensure_api_key()

    agent = JournalAgent(journal_dir=journal_dir, model=model)

    console.print()
    label = "weekly" if period == "week" else period
    with console.status(
        f"[bold green]Generating your {label} reflection...[/]", spinner="dots"
    ):
        reflection = agent.generate_weekly_reflection()

    console.print(
        Panel(
            Markdown(reflection),
            title=f"[bold magenta]Your {label.capitalize()} Reflection[/]",
            border_style="magenta",
            padding=(1, 2),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_api_key() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print(
            "[bold red]Error:[/] ANTHROPIC_API_KEY environment variable is not set.\n"
            "Export it before running journal-agent:",
        )
        console.print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)


def _build_analysis_renderable(
    mood: str,
    themes: list[str],
    summary: str,
) -> Text:
    t = Text()
    t.append("Mood:    ", style="bold")
    t.append(f"{mood}\n", style=_mood_style(mood))
    t.append("Themes:  ", style="bold")
    t.append(", ".join(themes) if themes else "(none detected)")
    t.append("\n")
    t.append("Summary: ", style="bold")
    t.append(summary)
    return t


_MOOD_STYLES: dict[str, str] = {
    "joyful": "bold yellow",
    "excited": "bold yellow",
    "grateful": "bold green",
    "content": "green",
    "reflective": "cyan",
    "neutral": "white",
    "anxious": "bold orange3",
    "overwhelmed": "bold orange3",
    "sad": "blue",
    "angry": "bold red",
}


def _mood_style(mood: str) -> str:
    return _MOOD_STYLES.get(mood.lower(), "white")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
