# openbimdl/cli.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import print

app = typer.Typer(
    name="openbimdl",
    help="OpenBIM-DL Runtime (CLI) — reference implementation for executing .obimdl recipes on IFC models.",
    no_args_is_help=True,
)

VERSION = "0.2.0"


@app.command("version")
def version() -> None:
    """Print runtime version."""
    print(f"[bold]openbimdl[/bold] runtime v{VERSION}")


@app.command("run")
def run(
    model: Path = typer.Argument(..., exists=True, readable=True, help="Path to input IFC (.ifc) file"),
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
    out: Path = typer.Option(Path("./out"), "--out", "-o", help="Output directory for generated artifacts"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Optional seed for synthesize operations"),
) -> None:
    """
    Execute a recipe against an IFC model and export datasets.

    Note: This is a stub in v0.2.0 (pre-alpha). It validates arguments and prepares the run context.
    """
    out.mkdir(parents=True, exist_ok=True)

    print("[bold]OpenBIM-DL Runtime[/bold] — run")
    print(f"Model : {model}")
    print(f"Recipe: {recipe}")
    print(f"Out   : {out}")
    print(f"Seed  : {seed if seed is not None else '(not set)'}")

    # TODO (v0.2): implement pipeline
    # 1) parse recipe -> AST
    # 2) type check
    # 3) load IFC
    # 4) build graph
    # 5) evaluate
    # 6) export
    # 7) manifest
    print("\n[yellow]Runtime pipeline not implemented yet.[/yellow]")
    raise typer.Exit(code=2)


@app.command("validate")
def validate(
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
) -> None:
    """
    Validate a recipe (syntax + types).

    Note: This is a stub in v0.2.0 (pre-alpha).
    """
    print("[bold]OpenBIM-DL Runtime[/bold] — validate")
    print(f"Recipe: {recipe}")

    # TODO: parse + type check
    print("\n[yellow]Validation not implemented yet.[/yellow]")
    raise typer.Exit(code=2)


@app.command("explain")
def explain(
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
) -> None:
    """
    Explain the execution plan for a recipe (what will run, what will be exported).

    Note: This is a stub in v0.2.0 (pre-alpha).
    """
    print("[bold]OpenBIM-DL Runtime[/bold] — explain")
    print(f"Recipe: {recipe}")

    # TODO: parse + build compile plan + show it
    print("\n[yellow]Explain not implemented yet.[/yellow]")
    raise typer.Exit(code=2)
