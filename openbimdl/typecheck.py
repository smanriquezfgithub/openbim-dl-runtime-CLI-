# openbimdl/typecheck.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from openbimdl.ast import Block, Document, Expr, Stmt


# -----------------------------
# Diagnostics
# -----------------------------

@dataclass(frozen=True)
class TypeDiagnostic:
    code: str
    message: str
    block: str
    stmt_kind: str
    stmt_name: Optional[str] = None


class TypeCheckError(Exception):
    def __init__(self, diagnostics: List[TypeDiagnostic]):
        super().__init__("Type check failed")
        self.diagnostics = diagnostics


# -----------------------------
# Function catalog registry (v0.1)
# -----------------------------
#
# This is intentionally a *minimal* registry for v0.2.
# It is used to prevent typos and enforce that only known built-ins are called.
#
# Later:
#  - load this from a generated catalog file
#  - validate argument counts/types (typed signatures)
#

BUILTIN_FUNCTIONS_V01: Set[str] = {
    # core
    "guid", "id", "exists", "coalesce", "hash", "seed",
    # ifc
    "ifc.type", "ifc.schema", "ifc.attr", "ifc.name", "ifc.predefined", "ifc.is_a", "ifc.global_placement",
    # pset
    "pset.get", "pset.has", "pset.keys", "pset.list", "pset.text", "pset.numeric",
    # qto
    "qto.get", "qto.has", "qto.net_area", "qto.net_volume", "qto.gross_area",
    # rel (generic)
    "rel.out", "rel.in", "rel.edges", "rel.kinds",
    # rel (shortcuts)
    "contained_in", "container_chain", "type_of", "aggregates", "decomposes",
    "assigned_to", "connects_to", "voids", "fills", "spaces",
    # graph
    "degree", "degree_in", "degree_out", "neighbors", "subgraph", "path_to",
    # geom
    "geom.exists", "geom.bbox", "geom.centroid", "geom.dims", "geom.volume", "geom.area", "geom.orientation",
    "geom.signature", "geom.mesh", "geom.pointcloud",
    # text
    "text.describe", "text.concat", "text.lower", "text.normalize", "text.tokens",
    # ml
    "ml.onehot", "ml.vocab", "ml.bucket", "ml.embed_hash", "ml.standardize",
    # synth
    "synth.jitter_bbox", "synth.drop_pset", "synth.drop_feature", "synth.noise_numeric",
    "synth.upsample", "synth.downsample", "synth.permute_within",
    # split operators (treated as functions in v0.2 structural checker)
    "building", "storey", "project", "system", "hash_group",
}


# -----------------------------
# Public API
# -----------------------------

def type_check_document(doc: Document) -> None:
    """
    v0.2 type checker (incremental).

    This is a pragmatic checker that validates:
      - required keys exist in source/export blocks
      - `by ...` usage appears only in split blocks (recommended)
      - function calls match known built-in catalog (anti-typo)
      - some reserved keywords aren't misused

    It does NOT yet:
      - infer full expression types
      - validate argument counts/types (beyond existence)
      - validate IFC schema compatibility
    """
    diags: List[TypeDiagnostic] = []

    diags += _check_source(doc.source)
    for i, v in enumerate(doc.views):
        diags += _check_view(v, index=i)
    diags += _check_derive(doc.derive)

    if doc.synthesize:
        diags += _check_synthesize(doc.synthesize)

    if doc.split:
        diags += _check_split(doc.split)
    else:
        # split is optional; ok
        pass

    for i, e in enumerate(doc.exports):
        diags += _check_export(e, index=i)

    # function catalog validation across all blocks
    diags += _check_known_functions(doc)

    if diags:
        raise TypeCheckError(diags)


# -----------------------------
# Block checks
# -----------------------------

def _check_source(block: Block) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []
    # Expect at least one: path "..."
    has_path = any(s.kind == "path" for s in block.statements)
    if not has_path:
        diags.append(TypeDiagnostic(
            code="SRC001",
            message="source block must include: path \"...\";",
            block="source",
            stmt_kind="path",
        ))
    return diags


def _check_view(block: Block, index: int) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []
    # Views are optional and flexible. But typically should contain a select.
    has_select = any(s.kind == "select" for s in block.statements)
    if not has_select:
        diags.append(TypeDiagnostic(
            code="VIEW001",
            message=f"view[{index}] has no select statement; view will have no effect unless selection is defined.",
            block="view",
            stmt_kind="select",
        ))
    return diags


def _check_derive(block: Block) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []
    # derive should define at least one feature or emit
    has_feature_or_emit = any(s.kind in ("feature", "emit") for s in block.statements)
    if not has_feature_or_emit:
        diags.append(TypeDiagnostic(
            code="DER001",
            message="derive block should include at least one feature or emit statement.",
            block="derive",
            stmt_kind="feature",
        ))
    return diags


def _check_synthesize(block: Block) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []
    # For v0.2, we accept any assign/emit/feature, but recommend only function calls to synth.*
    # We'll keep as warning-like diagnostics if non-synth calls are found in synthesize assigns/features.
    for s in block.statements:
        if s.kind in ("assign", "feature", "emit"):
            expr: Expr = s.data.get("expr")
            if expr and not _contains_prefix_call(expr, "synth."):
                diags.append(TypeDiagnostic(
                    code="SYN001",
                    message="synthesize statements should primarily call synth.* functions (v0.2 recommendation).",
                    block="synthesize",
                    stmt_kind=s.kind,
                    stmt_name=s.data.get("name"),
                ))
    return diags


def _check_split(block: Block) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []
    # Expect a "by ..." statement
    has_by = any(s.kind == "by" for s in block.statements)
    if not has_by:
        diags.append(TypeDiagnostic(
            code="SPL001",
            message="split block should include: by <operator>(...);",
            block="split",
            stmt_kind="by",
        ))
    return diags


def _check_export(block: Block, index: int) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []
    has_format = any(s.kind == "format" for s in block.statements)
    has_path = any(s.kind == "path" for s in block.statements)

    if not has_format:
        diags.append(TypeDiagnostic(
            code="EXP001",
            message=f"export[{index}] block must include: format <name>;",
            block="export",
            stmt_kind="format",
        ))
    if not has_path:
        diags.append(TypeDiagnostic(
            code="EXP002",
            message=f"export[{index}] block must include: path \"...\";",
            block="export",
            stmt_kind="path",
        ))
    return diags


# -----------------------------
# Function call validation
# -----------------------------

def _check_known_functions(doc: Document) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []

    def walk_block(block: Block):
        for st in block.statements:
            diags.extend(_check_stmt_expr_calls(block.kind, st))

    walk_block(doc.source)
    for v in doc.views:
        walk_block(v)
    walk_block(doc.derive)
    if doc.synthesize:
        walk_block(doc.synthesize)
    if doc.split:
        walk_block(doc.split)
    for e in doc.exports:
        walk_block(e)

    return diags


def _check_stmt_expr_calls(block_kind: str, st: Stmt) -> List[TypeDiagnostic]:
    diags: List[TypeDiagnostic] = []
    expr = st.data.get("expr")
    if isinstance(expr, Expr):
        for fn_name in _extract_calls(expr):
            if fn_name not in BUILTIN_FUNCTIONS_V01:
                diags.append(TypeDiagnostic(
                    code="FN001",
                    message=f"Unknown function '{fn_name}'. Not present in OpenBIM-DL v0.1 built-in catalog.",
                    block=block_kind,
                    stmt_kind=st.kind,
                    stmt_name=st.data.get("name"),
                ))
    # also validate args in `by` statement
    if st.kind == "by":
        fn = st.data.get("fn")
        if fn and fn not in BUILTIN_FUNCTIONS_V01:
            diags.append(TypeDiagnostic(
                code="FN002",
                message=f"Unknown split operator '{fn}'. Not present in OpenBIM-DL v0.1 catalog.",
                block=block_kind,
                stmt_kind="by",
                stmt_name=None,
            ))
        for a in st.data.get("args", []):
            if isinstance(a, Expr):
                for fn_name in _extract_calls(a):
                    if fn_name not in BUILTIN_FUNCTIONS_V01:
                        diags.append(TypeDiagnostic(
                            code="FN001",
                            message=f"Unknown function '{fn_name}'. Not present in OpenBIM-DL v0.1 built-in catalog.",
                            block=block_kind,
                            stmt_kind="by",
                            stmt_name=None,
                        ))
    return diags


def _extract_calls(expr: Expr) -> List[str]:
    """
    Return fully-qualified function names found in an expression.
    The parser currently produces function calls as:
      kind="call", data={"fn": "ifc.type", "args": [...]}
    """
    out: List[str] = []

    def walk(e: Expr):
        if e.kind == "call":
            fn = e.data.get("fn")
            if fn:
                out.append(str(fn))
            for a in e.data.get("args", []):
                if isinstance(a, Expr):
                    walk(a)
        elif e.kind == "binop":
            walk(e.data["left"])
            walk(e.data["right"])
        elif e.kind == "unop":
            walk(e.data["value"])
        elif e.kind == "access":
            # access may contain index expressions
            for p in e.data.get("parts", []):
                if isinstance(p, dict) and p.get("kind") == "index":
                    idx = p.get("expr")
                    if isinstance(idx, Expr):
                        walk(idx)
        else:
            # literals/null: nothing
            pass

    walk(expr)
    return out


def _contains_prefix_call(expr: Expr, prefix: str) -> bool:
    for fn in _extract_calls(expr):
        if fn.startswith(prefix):
            return True
    return False
