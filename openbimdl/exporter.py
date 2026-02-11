# openbimdl/exporter.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import json

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except Exception as e:  # pragma: no cover
    pa = None
    pq = None


class ExportError(Exception):
    pass


@dataclass(frozen=True)
class ExportResult:
    format: str
    path: str
    rows: Optional[int] = None
    cols: Optional[int] = None


def export_tabular_parquet(
    rows: List[Dict[str, Any]],
    out_path: str | Path,
) -> ExportResult:
    """
    Export a list-of-dicts tabular dataset to Parquet using PyArrow.

    - Supports None values (written as null)
    - Columns are inferred from union of keys
    """
    if pa is None or pq is None:
        raise ExportError("pyarrow is required for Parquet export. Install: pip install pyarrow")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        # write empty table with no columns
        table = pa.table({})
        pq.write_table(table, str(out_path))
        return ExportResult(format="parquet", path=str(out_path), rows=0, cols=0)

    # Union of keys across rows -> stable column set
    cols = _union_columns(rows)

    # Build column arrays
    data = {c: [r.get(c, None) for r in rows] for c in cols}

    table = pa.Table.from_pydict(data)
    pq.write_table(table, str(out_path))

    return ExportResult(format="parquet", path=str(out_path), rows=len(rows), cols=len(cols))


def export_tabular_jsonl(
    rows: List[Dict[str, Any]],
    out_path: str | Path,
) -> ExportResult:
    """
    Export list-of-dicts to JSON Lines (one JSON object per line).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False))
            f.write("\n")

    cols = len(_union_columns(rows)) if rows else 0
    return ExportResult(format="jsonl", path=str(out_path), rows=len(rows), cols=cols)


def export_edge_list_tsv(
    edges: Sequence[Tuple[str, str, str]],
    out_path: str | Path,
    header: bool = True,
) -> ExportResult:
    """
    Export graph edges as TSV:
      source_guid  target_guid  edge_type
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        if header:
            f.write("source_guid\ttarget_guid\tedge_type\n")
        for s, t, k in edges:
            f.write(f"{s}\t{t}\t{k}\n")

    return ExportResult(format="edge_list_tsv", path=str(out_path), rows=len(edges), cols=3 if edges else 0)


def export_manifest_json(
    manifest: Dict[str, Any],
    out_path: str | Path,
) -> ExportResult:
    """
    Export manifest as pretty JSON (deterministic key order).
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    return ExportResult(format="json", path=str(out_path), rows=None, cols=None)


# -------------------------
# Helpers
# -------------------------

def _union_columns(rows: List[Dict[str, Any]]) -> List[str]:
    cols = set()
    for r in rows:
        cols.update(r.keys())
    # Prefer stable: guid first if present, then alphabetical
    ordered = []
    if "guid" in cols:
        ordered.append("guid")
        cols.remove("guid")
    ordered.extend(sorted(cols))
    return ordered
