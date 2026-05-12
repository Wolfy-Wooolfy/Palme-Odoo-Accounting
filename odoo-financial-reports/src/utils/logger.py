import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Force UTF-8 output so Unicode symbols work on Windows cp1252 terminals
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf-8-sig"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

console = Console(highlight=False)


def info(msg: str) -> None:
    console.print(f"[cyan]ℹ[/cyan]  {msg}")


def success(msg: str) -> None:
    console.print(f"[green]✓[/green]  {msg}")


def warning(msg: str) -> None:
    console.print(f"[yellow]⚠[/yellow]  {msg}")


def error(msg: str) -> None:
    console.print(f"[red]✗[/red]  {msg}")


def debug(msg: str) -> None:
    console.print(f"[dim]·  {msg}[/dim]")


def section(title: str) -> None:
    console.print()
    console.print(Panel(
        Text(title, style="bold white"),
        border_style="blue",
        expand=False,
        padding=(0, 2),
    ))
