# openbimdl/ast.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Literal


# -----------------------------
# Expression model (lightweight)
# -----------------------------

ExprKind = Literal["number", "string", "bool", "null", "call", "access", "binop", "unop"]


@dataclass(frozen=True)
class Expr:
    """
    Lightweight expression node used by the parser stage.

    This is not a full semantic IR yet (no type info).
    It is sufficient for:
      - building a Typed AST later
      - printing/debugging
      - implementing a type checker incrementally
    """
    kind: ExprKind
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_raw(raw: Any) -> "Expr":
        """
        Convert the parser output expression dict to Expr.
        The parser returns dicts like:
          {"_expr": "binop", "op": "+", "left": ..., "right": ...}
        """
        if isinstance(raw, Expr):
            return raw

        if not isinstance(raw, dict) or "_expr" not in raw:
            # Defensive: treat unknown as null
            return Expr(kind="null", data={"value": None})

        kind = raw["_expr"]
        if kind not in ("number", "string", "bool", "null", "call", "access", "binop", "unop"):
            return Expr(kind="null", data={"value": None})

        # Recursively convert nested expressions
        if kind == "binop":
            return Expr(
                kind="binop",
                data={
                    "op": raw.get("op"),
                    "left": Expr.from_raw(raw.get("left")),
                    "right": Expr.from_raw(raw.get("right")),
                },
            )

        if kind == "unop":
            return Expr(
                kind="unop",
                data={
                    "op": raw.get("op"),
                    "value": Expr.from_raw(raw.get("value")),
                },
            )

        if kind == "call":
            args = [Expr.from_raw(a) for a in raw.get("args", [])]
            return Expr(kind="call", data={"fn": raw.get("fn"), "args": args})

        if kind == "access":
            # parts may include index expressions
            parts = []
            for p in raw.get("parts", []):
                if isinstance(p, dict) and p.get("kind") == "index":
                    parts.append({"kind": "index", "expr": Expr.from_raw(p.get("expr"))})
                else:
                    parts.append(p)
            return Expr(kind="access", data={"parts": parts})

        # literals
        return Expr(kind=kind, data={"value": raw.get("value")})


# -----------------------------
# Statements
# -----------------------------

StmtKind = Literal[
    "assign",
    "emit",
    "select",
    "where",
    "label",
    "format",
    "path",
    "by",
    "feature",
    "node_features",
    "edge_features",
]


@dataclass(frozen=True)
class Stmt:
    kind: StmtKind
    data: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_raw(raw: Dict[str, Any]) -> "Stmt":
        """
        Convert parser statement dict into Stmt with Expr nodes where applicable.
        """
        kind = raw.get("type")
        if kind not in (
            "assign",
            "emit",
            "select",
            "where",
            "label",
            "format",
            "path",
            "by",
            "feature",
            "node_features",
            "edge_features",
        ):
            # Unknown statements are ignored upstream; keep as assign null for safety
            return Stmt(kind="assign", data={"name": "__invalid__", "expr": Expr(kind="null")})

        if kind in ("assign", "emit", "select", "where", "label", "feature"):
            data = dict(raw)
            if "expr" in data:
                data["expr"] = Expr.from_raw(data["expr"])
            return Stmt(kind=kind, data=data)

        if kind == "by":
            data = dict(raw)
            data["args"] = [Expr.from_raw(a) for a in data.get("args", [])]
            return Stmt(kind="by", data=data)

        if kind in ("node_features", "edge_features"):
            features = []
            for f in raw.get("features", []):
                # each feature is like {"type":"feature","name":...,"expr":...}
                if isinstance(f, dict):
                    features.append(Stmt.from_raw(f))
            return Stmt(kind=kind, data={"features": features})

        # format/path are pure
        return Stmt(kind=kind, data=dict(raw))


# -----------------------------
# Blocks
# -----------------------------

BlockKind = Literal["source", "view", "derive", "synthesize", "split", "export"]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    statements: List[Stmt] = field(default_factory=list)

    @staticmethod
    def from_raw(kind: BlockKind, body: List[Dict[str, Any]]) -> "Block":
        stmts: List[Stmt] = []
        for s in body or []:
            if isinstance(s, dict) and "type" in s:
                stmts.append(Stmt.from_raw(s))
        return Block(kind=kind, statements=stmts)


# -----------------------------
# Document
# -----------------------------

@dataclass(frozen=True)
class Document:
    source: Block
    views: List[Block]
    derive: Block
    synthesize: Optional[Block]
    split: Optional[Block]
    exports: List[Block]

    @staticmethod
    def from_parsed(parsed: Dict[str, Any]) -> "Document":
        """
        Build a Document from parser output structure.

        Expected shape:
          {
            "source": {"_kind":"source","body":[...]},
            "views": [{"_kind":"view","body":[...]}, ...],
            "derive": {"_kind":"derive","body":[...]},
            "synthesize": {"_kind":"synthesize","body":[...]} | None,
            "split": {"_kind":"split","body":[...]} | None,
            "exports": [{"_kind":"export","body":[...]}, ...]
          }
        """
        if parsed.get("source") is None:
            raise ValueError("Recipe is missing required 'source' block.")
        if parsed.get("derive") is None:
            raise ValueError("Recipe is missing required 'derive' block.")
        if not parsed.get("exports"):
            raise ValueError("Recipe must include at least one 'export' block.")

        source = Block.from_raw("source", parsed["source"]["body"])
        views = [Block.from_raw("view", v["body"]) for v in parsed.get("views", [])]
        derive = Block.from_raw("derive", parsed["derive"]["body"])

        synth = parsed.get("synthesize")
        split = parsed.get("split")

        synth_block = Block.from_raw("synthesize", synth["body"]) if synth else None
        split_block = Block.from_raw("split", split["body"]) if split else None

        exports = [Block.from_raw("export", e["body"]) for e in parsed.get("exports", [])]

        return Document(
            source=source,
            views=views,
            derive=derive,
            synthesize=synth_block,
            split=split_block,
            exports=exports,
        )

    def summary(self) -> Dict[str, Any]:
        """
        Small helper for `openbimdl explain` (later).
        """
        return {
            "blocks": {
                "source": len(self.source.statements),
                "views": [len(v.statements) for v in self.views],
                "derive": len(self.derive.statements),
                "synthesize": len(self.synthesize.statements) if self.synthesize else 0,
                "split": len(self.split.statements) if self.split else 0,
                "exports": [len(e.statements) for e in self.exports],
            }
        }
