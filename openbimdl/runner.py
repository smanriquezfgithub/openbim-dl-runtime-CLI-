# openbimdl/runner.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import time

from openbimdl.ast import Document
from openbimdl.evaluator import Evaluator
from openbimdl.exporter import (
    ExportResult,
    export_edge_list_tsv,
    export_manifest_json,
    export_tabular_jsonl,
    export_tabular_parquet,
)
from openbimdl.graph import SemanticGraph
from openbimdl.ifc_loader import IFCModel
from openbimdl.parser import RecipeParseError, parse_recipe_file
from openbimdl.typecheck import TypeCheckError, type_check_document


class RunError(Exception):
    pass


@dataclass(frozen=True)
class RunOutputs:
    artifacts: List[ExportResult]
    manifest_path: str


@dataclass
class RunContext:
    model_path: str
    recipe_path: str
    out_dir: str
    seed: Optional[int]
    rel_whitelist: List[str]


# -----------------------------
# Public API
# -----------------------------

def run_recipe(
    model_path: str | Path,
    recipe_path: str | Path,
    out_dir: str | Path,
    *,
    seed: Optional[int] = None,
    rel_whitelist: Optional[List[str]] = None,
) -> RunOutputs:
    """
    Execute OpenBIM-DL recipe against an IFC model.

    v0.2 MVP pipeline:
      1) parse recipe
      2) build AST
      3) typecheck (minimal)
      4) load IFC
      5) build semantic graph
      6) evaluate derive over selected nodes
      7) export artifacts (parquet/jsonl/edge_list where applicable)
      8) write manifest.json

    Notes:
      - synthesize + split are not executed yet (planned).
      - export types supported now:
          - parquet (tabular)
          - jsonl (tabular)
          - edge_list_tsv (graph edges)
    """
    model_path = Path(model_path)
    recipe_path = Path(recipe_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rel_whitelist = rel_whitelist or ["contained_in", "aggregates", "type_of", "connects_to"]

    ctx = RunContext(
        model_path=str(model_path),
        recipe_path=str(recipe_path),
        out_dir=str(out_dir),
        seed=seed,
        rel_whitelist=rel_whitelist,
    )

    t0 = time.time()

    # 1) Parse
    parsed, recipe_text = _parse_recipe(recipe_path)

    # 2) AST
    doc = Document.from_parsed(parsed)

    # 3) Typecheck
    _typecheck(doc)

    t_parse = time.time()

    # 4) Load IFC
    ifc = IFCModel(model_path)
    t_ifc = time.time()

    # 5) Build graph
    graph = SemanticGraph(ifc, rel_whitelist=rel_whitelist)
    t_graph = time.time()

    # 6) Evaluate
    evaluator = Evaluator(ifc, graph)
    rows = evaluator.evaluate(doc)
    t_eval = time.time()

    # 7) Export
    artifacts: List[ExportResult] = []
    artifacts += _execute_exports(doc, rows, graph, out_dir)

    # 8) Manifest
    manifest = _build_manifest(
        ctx=ctx,
        recipe_text=recipe_text,
        ifc_model=ifc,
        graph=graph,
        rows=rows,
        artifacts=artifacts,
        timings={
            "parse_ast_typecheck_s": round(t_parse - t0, 6),
            "ifc_load_s": round(t_ifc - t_parse, 6),
            "graph_build_s": round(t_graph - t_ifc, 6),
            "evaluate_s": round(t_eval - t_graph, 6),
            "total_s": round(time.time() - t0, 6),
        },
    )

    manifest_path = out_dir / "manifest.json"
    export_manifest_json(manifest, manifest_path)

    return RunOutputs(artifacts=artifacts, manifest_path=str(manifest_path))


# -----------------------------
# Steps
# -----------------------------

def _parse_recipe(recipe_path: Path) -> Tuple[Dict[str, Any], str]:
    try:
        parsed = parse_recipe_file(recipe_path)
        recipe_text = recipe_path.read_text(encoding="utf-8")
        return parsed, recipe_text
    except RecipeParseError as e:
        d = e.diagnostic
        raise RunError(f"Parse error: {d.message}\n\n{d.context}") from e
    except Exception as e:
        raise RunError(f"Failed to read/parse recipe: {e}") from e


def _typecheck(doc: Document) -> None:
    try:
        type_check_document(doc)
    except TypeCheckError as e:
        msg = "\n".join(
            f"- {d.code} [{d.block}:{d.stmt_kind}] {d.message}"
            for d in e.diagnostics
        )
        raise RunError(f"Type check failed:\n{msg}") from e


def _execute_exports(doc: Document, rows: List[Dict[str, Any]], graph: SemanticGraph, out_dir: Path) -> List[ExportResult]:
    results: List[ExportResult] = []

    for export_block in doc.exports:
        fmt = _export_get_value(export_block, "format")
        path = _export_get_value(export_block, "path")

        if not fmt or not path:
            # typechecker should have caught this
            continue

        out_path = (out_dir / path) if not Path(path).is_absolute() else Path(path)

        if fmt == "parquet":
            results.append(export_tabular_parquet(rows, out_path))

        elif fmt == "jsonl":
            results.append(export_tabular_jsonl(rows, out_path))

        elif fmt == "edge_list":
            # v0.2: export edge list TSV of graph edges
            edges = graph.edge_list()
            results.append(export_edge_list_tsv(edges, out_path.with_suffix(".tsv")))

        else:
            raise RunError(f"Unsupported export format in v0.2: {fmt}")

    return results


def _export_get_value(block, kind: str) -> Optional[str]:
    """
    Find first statement in export block: format <x>; or path "<x>";
    Parser stores these as Stmt(kind="format"/"path", data={"value": ...})
    """
    for st in block.statements:
        if st.kind == kind:
            return st.data.get("value")
    return None


# -----------------------------
# Manifest helpers
# -----------------------------

def _build_manifest(
    ctx: RunContext,
    recipe_text: str,
    ifc_model: IFCModel,
    graph: SemanticGraph,
    rows: List[Dict[str, Any]],
    artifacts: List[ExportResult],
    timings: Dict[str, Any],
) -> Dict[str, Any]:
    recipe_hash = _sha256_text(recipe_text)
    ifc_hash = _sha256_file(ctx.model_path)

    return {
        "openbimdl_runtime": {
            "version": "0.2.0",
            "mode": "cli",
        },
        "inputs": {
            "ifc": {
                "path": ctx.model_path,
                "sha256": ifc_hash,
                "schema": ifc_model.schema(),
            },
            "recipe": {
                "path": ctx.recipe_path,
                "sha256": recipe_hash,
            },
        },
        "config": {
            "seed": ctx.seed,
            "rel_whitelist": ctx.rel_whitelist,
        },
        "stats": {
            "ifc": ifc_model.stats(),
            "graph": graph.stats(),
            "dataset": {
                "rows": len(rows),
                "cols": len(rows[0].keys()) if rows else 0,
            },
        },
        "artifacts": [
            {
                "format": a.format,
                "path": a.path,
                "rows": a.rows,
                "cols": a.cols,
            }
            for a in artifacts
        ],
        "timings": timings,
    }


def _sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
