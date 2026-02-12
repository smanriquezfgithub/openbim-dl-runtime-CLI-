# openbimdl/parser.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Union

from lark import Lark, Transformer, Token
from lark.exceptions import LarkError, UnexpectedInput


# -----------------------------
# Public API
# -----------------------------

@dataclass(frozen=True)
class ParseDiagnostic:
    message: str
    line: int
    column: int
    context: str


class RecipeParseError(Exception):
    def __init__(self, diagnostic: ParseDiagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic


def parse_recipe_text(text: str) -> Dict[str, Any]:
    """
    Parse OpenBIM-DL v0.1 recipe text and return a normalized structure.

    Output shape (parser-level):
      - source: {"_kind":"source","body":[stmts]}
      - views: [{"_kind":"view","name":str,"body":[stmts]}...]
      - derive: {"_kind":"derive","body":[assign...]}
      - synthesize: {"_kind":"synthesize","body":[assign...]} | None
      - split: {"_kind":"split","body":[assign...]} | None
      - exports: [{"_kind":"export","kind":str,"body":[assign...]}...]

    Notes:
      - This is syntactic parsing + lightweight expression AST.
      - Semantics/type validation are handled by ast.py / typecheck.py.
    """
    try:
        tree = _PARSER.parse(text)
        data = _ToDictTransformer().transform(tree)
        return data
    except UnexpectedInput as e:
        diag = _to_diagnostic(text, e)
        raise RecipeParseError(diag) from e
    except LarkError as e:
        diag = ParseDiagnostic(
            message=f"Parse error: {e}",
            line=1,
            column=1,
            context=text[:200],
        )
        raise RecipeParseError(diag) from e


def parse_recipe_file(path: Union[str, Path]) -> Dict[str, Any]:
    path = Path(path)
    return parse_recipe_text(path.read_text(encoding="utf-8"))


# -----------------------------
# Grammar (OpenBIM-DL v0.1 — spec canonical)
# -----------------------------
#
# Document:
#   source { ... }
#   view <Name> { select node|edge; where <expr>; ... }
#   derive { <name> = <expr>; ... }
#   synthesize? { ... }   (parsed, may be ignored by runtime v0.2)
#   split? { ... }        (parsed, may be ignored by runtime v0.2)
#   export <kind> { format="parquet"; path="..."; ... }  (kind: tabular|graph|text)
#
# Statements:
#   - assign: IDENT "=" expr ";"
#   - view: select + where (and optional assigns inside view if spec allows later)
#
# Comments:
#   - line comments starting with '#'
#

_OPENBIMDL_GRAMMAR = r"""
?start: document

document: source_block view_block* derive_block synthesize_block? split_block? export_block+

source_block: "source" block

view_block: "view" IDENT view_block_body
view_block_body: "{" view_stmt* "}"

derive_block: "derive" block
synthesize_block: "synthesize" block
split_block: "split" block

export_block: "export" IDENT block

block: "{" assign_stmt* "}"

?view_stmt: select_stmt
         | where_stmt
         | assign_stmt    -> view_assign_stmt

select_stmt: "select" ("node" | "edge") ";"
where_stmt: "where" expr ";"

assign_stmt: IDENT "=" expr ";"

# -----------------------------
# Expressions (operators + calls + access)
# -----------------------------

?expr: logic_or

?logic_or: logic_and
         | logic_or "or" logic_and   -> or_op

?logic_and: logic_not
          | logic_and "and" logic_not -> and_op

?logic_not: comparison
          | "not" logic_not          -> not_op

?comparison: sum
           | comparison "==" sum     -> eq
           | comparison "!=" sum     -> ne
           | comparison "<"  sum     -> lt
           | comparison ">"  sum     -> gt
           | comparison "<=" sum     -> le
           | comparison ">=" sum     -> ge

?sum: term
    | sum "+" term                   -> add
    | sum "-" term                   -> sub

?term: factor
     | term "*" factor               -> mul
     | term "/" factor               -> div
     | term "%" factor               -> mod

?factor: atom
       | "-" factor                  -> neg

?atom: literal
     | func_call
     | access
     | "(" expr ")"

func_call: IDENT "(" [arg_list] ")"

access: IDENT ("." IDENT)* indexer*
indexer: "[" expr "]"

?arg_list: expr ("," expr)*

?literal: NUMBER      -> number
        | STRING      -> string
        | "true"      -> true
        | "false"     -> false
        | "null"      -> null

IDENT: /[A-Za-z_][A-Za-z0-9_]*/
STRING: ESCAPED_STRING

%import common.ESCAPED_STRING
%import common.SIGNED_NUMBER -> NUMBER
%import common.WS
%ignore WS

COMMENT: /#[^\n]*/
%ignore COMMENT
"""


# -----------------------------
# Transformer: parse tree -> dict
# -----------------------------

class _ToDictTransformer(Transformer):
    def document(self, items):
        out: Dict[str, Any] = {
            "source": None,
            "views": [],
            "derive": None,
            "synthesize": None,
            "split": None,
            "exports": [],
        }

        for it in items:
            kind = it.get("_kind")
            if kind == "source":
                out["source"] = it
            elif kind == "view":
                out["views"].append(it)
            elif kind == "derive":
                out["derive"] = it
            elif kind == "synthesize":
                out["synthesize"] = it
            elif kind == "split":
                out["split"] = it
            elif kind == "export":
                out["exports"].append(it)

        return out

    # --- blocks

    def source_block(self, items):
        return {"_kind": "source", "body": items[0]}

    def view_block(self, items):
        # items: IDENT, view_block_body(list of statements)
        name = str(items[0])
        body = items[1]
        return {"_kind": "view", "name": name, "body": body}

    def view_block_body(self, items):
        return items

    def derive_block(self, items):
        return {"_kind": "derive", "body": items[0]}

    def synthesize_block(self, items):
        return {"_kind": "synthesize", "body": items[0]}

    def split_block(self, items):
        return {"_kind": "split", "body": items[0]}

    def export_block(self, items):
        # items: IDENT(kind), block(assigns)
        kind = str(items[0])
        body = items[1]
        return {"_kind": "export", "kind": kind, "body": body}

    def block(self, items):
        return items

    # --- statements

    def assign_stmt(self, items):
        name = str(items[0])
        expr = items[1]
        return {"type": "assign", "name": name, "expr": expr}

    def view_assign_stmt(self, items):
        # same payload as assign_stmt, but tag where it came from
        st = items[0]
        st["in_view"] = True
        return st

    def select_stmt(self, items):
        # items: "node" or "edge" token
        target = str(items[0])
        return {"type": "select", "target": target}

    def where_stmt(self, items):
        return {"type": "where", "expr": items[0]}

    def arg_list(self, items):
        return items

    # --- literals

    def number(self, items):
        return {"_expr": "number", "value": float(items[0])}

    def string(self, items):
        return {"_expr": "string", "value": _unquote(str(items[0]))}

    def true(self, _):
        return {"_expr": "bool", "value": True}

    def false(self, _):
        return {"_expr": "bool", "value": False}

    def null(self, _):
        return {"_expr": "null", "value": None}

    # --- expressions

    def func_call(self, items):
        fn = str(items[0])
        args = items[1:] and items[1] or []
        if isinstance(args, list):
            pass
        else:
            args = [args]
        return {"_expr": "call", "fn": fn, "args": args}

    def access(self, items):
        # access: IDENT ("." IDENT)* indexer*
        base = str(items[0])
        parts: List[Any] = [{"kind": "ident", "name": base}]
        for it in items[1:]:
            if isinstance(it, Token):
                parts.append({"kind": "attr", "name": str(it)})
            elif isinstance(it, dict) and it.get("_expr") == "index":
                parts.append({"kind": "index", "expr": it["expr"]})
            else:
                parts.append({"kind": "unknown", "value": it})
        return {"_expr": "access", "parts": parts}

    def indexer(self, items):
        return {"_expr": "index", "expr": items[0]}

    # --- operators

    def _binop(self, op: str, items):
        return {"_expr": "binop", "op": op, "left": items[0], "right": items[1]}

    def add(self, items): return self._binop("+", items)
    def sub(self, items): return self._binop("-", items)
    def mul(self, items): return self._binop("*", items)
    def div(self, items): return self._binop("/", items)
    def mod(self, items): return self._binop("%", items)

    def eq(self, items): return self._binop("==", items)
    def ne(self, items): return self._binop("!=", items)
    def lt(self, items): return self._binop("<", items)
    def gt(self, items): return self._binop(">", items)
    def le(self, items): return self._binop("<=", items)
    def ge(self, items): return self._binop(">=", items)

    def and_op(self, items): return self._binop("and", items)
    def or_op(self, items): return self._binop("or", items)

    def not_op(self, items):
        return {"_expr": "unop", "op": "not", "value": items[0]}

    def neg(self, items):
        return {"_expr": "unop", "op": "-", "value": items[0]}


# -----------------------------
# Internal helpers
# -----------------------------

_PARSER = Lark(
    _OPENBIMDL_GRAMMAR,
    parser="lalr",
    start="start",
    propagate_positions=True,
    maybe_placeholders=False,
)


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1].encode("utf-8").decode("unicode_escape")
    if len(s) >= 2 and s[0] == s[-1] == "'":
        return s[1:-1].encode("utf-8").decode("unicode_escape")
    return s


def _to_diagnostic(source: str, e: UnexpectedInput) -> ParseDiagnostic:
    line = getattr(e, "line", 1) or 1
    column = getattr(e, "column", 1) or 1
    lines = source.splitlines()
    context_line = lines[line - 1] if 0 <= line - 1 < len(lines) else ""
    pointer = " " * max(column - 1, 0) + "^"
    ctx = f"{context_line}\n{pointer}"
    msg = "Unexpected input"
    try:
        msg = str(e)
    except Exception:
        pass
    return ParseDiagnostic(
        message=msg,
        line=line,
        column=column,
        context=ctx,
    )
