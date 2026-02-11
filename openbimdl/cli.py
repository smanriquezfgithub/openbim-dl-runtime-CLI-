# openbimdl/cli.py
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from openbimdl.ast import Document
from openbimdl.parser import RecipeParseError, parse_recipe_file
from openbimdl.runner import RunError, run_recipe
from openbimdl.typecheck import TypeCheckError, type_check_document

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
    Validate a recipe (syntax + structural AST + minimal type check).
    """
    try:
        parsed = parse_recipe_file(recipe)
        doc = Document.from_parsed(parsed)
        type_check_document(doc)

    except RecipeParseError as e:
        d = e.diagnostic
        console.print(Panel.fit(f"[red]Parse error[/red]\n{d.message}\n\n{d.context}", title=str(recipe)))
        raise typer.Exit(code=1) from e

    except TypeCheckError as e:
        tbl = Table(title="Type check diagnostics", show_lines=True)
        tbl.add_column("Code", style="bold")
        tbl.add_column("Location")
        tbl.add_column("Message")

        for d in e.diagnostics:
            loc = f"{d.block}:{d.stmt_kind}" + (f" ({d.stmt_name})" if d.stmt_name else "")
            tbl.add_row(d.code, loc, d.message)

        console.print(Panel.fit("[red]Type check failed[/red]", title=str(recipe)))
        console.print(tbl)
        raise typer.Exit(code=1) from e

    except ValueError as e:
        console.print(Panel.fit(f"[red]Invalid recipe[/red]\n{e}", title=str(recipe)))
        raise typer.Exit(code=1) from e

    console.print(Panel.fit("[green]OK[/green] Recipe is valid (parse + AST + typecheck).", title="validate"))
    raise typer.Exit(code=0)


@app.command("explain")
def explain(
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
) -> None:
    """
    Explain recipe structure (blocks and statement counts).
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

    console.print("\n[dim]Note: explain shows structure only. Use validate for typecheck.[/dim]")
    raise typer.Exit(code=0)


@app.command("run")
def run(
    model: Path = typer.Argument(..., exists=True, readable=True, help="Path to input IFC (.ifc) file"),
    recipe: Path = typer.Argument(..., exists=True, readable=True, help="Path to OpenBIM-DL recipe (.obimdl) file"),
    out: Path = typer.Option(Path("./out"), "--out", "-o", help="Output directory for generated artifacts"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Optional seed for synthesize operations (planned)"),
) -> None:
    """
    Execute a recipe against an IFC model and export datasets (v0.2 MVP).
    """
    out.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit("[bold]OpenBIM-DL Runtime[/bold] — run", title="run"))
    console.print(f"Model : {model}")
    console.print(f"Recipe: {recipe}")
    console.print(f"Out   : {out}")
    console.print(f"Seed  : {seed if seed is not None else '(not set)'}\n")

    try:
        outputs = run_recipe(
            model_path=model,
            recipe_path=recipe,
            out_dir=out,
            seed=seed,
        )
    except RunError as e:
        console.print(Panel.fit(f"[red]Run failed[/red]\n{e}", title="run"))
        raise typer.Exit(code=1) from e
    except Exception as e:
        console.print(Panel.fit(f"[red]Unexpected error[/red]\n{e}", title="run"))
        raise typer.Exit(code=1) from e

    # Print artifacts
    tbl = Table(title="Generated artifacts", show_lines=True)
    tbl.add_column("Format", style="bold")
    tbl.add_column("Path")
    tbl.add_column("Rows", justify="right")
    tbl.add_column("Cols", justify="right")

    for a in outputs.artifacts:
        tbl.add_row(
            a.format,
            a.path,
            str(a.rows) if a.rows is not None else "-",
            str(a.cols) if a.cols is not None else "-",
        )

    console.print(tbl)
    console.print(Panel.fit(f"[green]OK[/green] Manifest written:\n{outputs.manifest_path}", title="run"))
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
