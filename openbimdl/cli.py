# openbimdl/cli.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel

from openbimdl.ast import Document
from openbimdl.parser import RecipeParseError, parse_recipe_file

app = typer.Typer(
    name="openbimdl",
    help="OpenBIM-DL Runtime (CLI) — reference implementation for executing .obimdl recipes on IFC models.",
    no_args_is_help=True,
)

VERSION = "0.2.0"
console = Console()


@app.command("version")
def version() -> None:
    """Print runtime version."""
    print(f"[bold]openbimdl[/bold] runtime v{VERSION}")


@app.command("validate")
def validate(
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
) -> None:
    """
    Validate a recipe (syntax + structural AST).

    v0.2.0 implements:
      - parsing
      - AST build (structural validation)
    Type checking is added in the next step.
    """
    try:
        parsed = parse_recipe_file(recipe)
        _ = Document.from_parsed(parsed)
    except RecipeParseError as e:
        d = e.diagnostic
        console.print(Panel.fit(f"[red]Parse error[/red]\n{d.message}\n\n{d.context}", title=str(recipe)))
        raise typer.Exit(code=1) from e
    except ValueError as e:
        console.print(Panel.fit(f"[red]Invalid recipe[/red]\n{e}", title=str(recipe)))
        raise typer.Exit(code=1) from e

    console.print(Panel.fit("[green]OK[/green] Recipe is syntactically valid and structurally complete.", title="validate"))
    raise typer.Exit(code=0)


@app.command("explain")
def explain(
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
) -> None:
    """
    Explain recipe structure (blocks and statement counts).

    v0.2.0 implements:
      - parsing
      - AST build
      - summary printing
    """
    try:
        parsed = parse_recipe_file(recipe)
        doc = Document.from_parsed(parsed)
    except RecipeParseError as e:
        d = e.diagnostic
        console.print(Panel.fit(f"[red]Parse error[/red]\n{d.message}\n\n{d.context}", title=str(recipe)))
        raise typer.Exit(code=1) from e
    except ValueError as e:
        console.print(Panel.fit(f"[red]Invalid recipe[/red]\n{e}", title=str(recipe)))
        raise typer.Exit(code=1) from e

    s = doc.summary()["blocks"]

    console.print(Panel.fit(f"[bold]Recipe:[/bold] {recipe}", title="explain"))

    console.print("[bold]Blocks[/bold]")
    console.print(f"  source      : {s['source']} statements")
    console.print(f"  views       : {len(s['views'])} view blocks -> {s['views']}")
    console.print(f"  derive      : {s['derive']} statements")
    console.print(f"  synthesize  : {s['synthesize']} statements")
    console.print(f"  split       : {s['split']} statements")
    console.print(f"  exports     : {len(s['exports'])} export blocks -> {s['exports']}")

    console.print("\n[dim]Note: v0.2.0 explain is structural only (no compile plan yet).[/dim]")
    raise typer.Exit(code=0)


@app.command("run")
def run(
    model: Path = typer.Argument(..., exists=True, readable=True, help="Path to input IFC (.ifc) file"),
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
    out: Path = typer.Option(Path("./out"), "--out", "-o", help="Output directory for generated artifacts"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Optional seed for synthesize operations"),
) -> None:
    """
    Execute a recipe against an IFC model and export datasets.

    Note: This remains a stub in v0.2.0 (pre-alpha).
    Next milestones:
      - add type checker
      - add IFC loader (IfcOpenShell)
      - build semantic graph
      - evaluate expressions
      - export engines
      - manifest
    """
    out.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit("[bold]OpenBIM-DL Runtime[/bold] — run", title="run"))
    console.print(f"Model : {model}")
    console.print(f"Recipe: {recipe}")
    console.print(f"Out   : {out}")
    console.print(f"Seed  : {seed if seed is not None else '(not set)'}")

    # Optional: validate recipe early (parse + structural)
    try:
        parsed = parse_recipe_file(recipe)
        _ = Document.from_parsed(parsed)
    except Exception as e:
        console.print(Panel.fit(f"[red]Cannot run[/red]\nRecipe invalid: {e}"))
        raise typer.Exit(code=1) from e

    console.print("\n[yellow]Runtime pipeline not implemented yet.[/yellow]")
    raise typer.Exit(code=2)
