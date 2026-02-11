# openbimdl/evaluator.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from openbimdl.ast import Document, Expr
from openbimdl.graph import SemanticGraph
from openbimdl.ifc_loader import IFCModel


class EvaluationError(Exception):
    pass


class Evaluator:
    """
    Minimal v0.2 evaluator.

    Supports:
      - view.select
      - view.where
      - derive.feature
    """

    def __init__(self, model: IFCModel, graph: SemanticGraph):
        self.model = model
        self.graph = graph

    # ---------------------------------------------------------
    # Entry point
    # ---------------------------------------------------------

    def evaluate(self, doc: Document) -> List[Dict[str, Any]]:
        """
        Return tabular dataset as list of dict rows.
        """

        # 1. Select nodes
        selected = self._apply_views(doc)

        # 2. Derive features
        dataset = self._apply_derive(doc, selected)

        return dataset

    # ---------------------------------------------------------
    # View handling
    # ---------------------------------------------------------

    def _apply_views(self, doc: Document):
        if not doc.views:
            # If no view defined, use all nodes
            return self.graph.nodes()

        result = []

        for view in doc.views:
            current = self.graph.nodes()

            for stmt in view.statements:
                if stmt.kind == "select":
                    type_name = stmt.data["type"]
                    current = self.graph.nodes_of_type(type_name)

                elif stmt.kind == "where":
                    expr = stmt.data["expr"]
                    current = [
                        node for node in current
                        if self._eval_expr(expr, node)
                    ]

            result.extend(current)

        # Deduplicate by guid
        seen = set()
        unique = []
        for n in result:
            if n.guid not in seen:
                seen.add(n.guid)
                unique.append(n)

        return unique

    # ---------------------------------------------------------
    # Derive handling
    # ---------------------------------------------------------

    def _apply_derive(self, doc: Document, nodes):
        dataset = []

        for node in nodes:
            row = {"guid": node.guid}

            for stmt in doc.derive.statements:
                if stmt.kind == "feature":
                    name = stmt.data["name"]
                    expr = stmt.data["expr"]
                    value = self._eval_expr(expr, node)
                    row[name] = value

            dataset.append(row)

        return dataset

    # ---------------------------------------------------------
    # Expression evaluation
    # ---------------------------------------------------------

    def _eval_expr(self, expr: Expr, node) -> Any:
        kind = expr.kind

        if kind == "literal":
            return expr.data["value"]

        if kind == "null":
            return None

        if kind == "binop":
            left = self._eval_expr(expr.data["left"], node)
            right = self._eval_expr(expr.data["right"], node)
            op = expr.data["op"]
            return self._apply_binop(op, left, right)

        if kind == "unop":
            val = self._eval_expr(expr.data["value"], node)
            op = expr.data["op"]
            return self._apply_unop(op, val)

        if kind == "call":
            fn = expr.data["fn"]
            args = [self._eval_expr(a, node) for a in expr.data["args"]]
            return self._dispatch_function(fn, node, args)

        if kind == "access":
            # v0.2 simplified: attribute access via IFC loader
            parts = expr.data["parts"]
            base = node

            for p in parts:
                if p["kind"] == "attr":
                    base = self.model.get_attr(
                        self.model.entity_by_guid(node.guid),
                        p["name"],
                    )
                else:
                    return None

            return base

        raise EvaluationError(f"Unsupported expression kind: {kind}")

    # ---------------------------------------------------------
    # Operators
    # ---------------------------------------------------------

    def _apply_binop(self, op, a, b):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b if b != 0 else None
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if op == "<":
            return a < b
        if op == ">":
            return a > b
        if op == "<=":
            return a <= b
        if op == ">=":
            return a >= b
        if op == "and":
            return bool(a) and bool(b)
        if op == "or":
            return bool(a) or bool(b)
        raise EvaluationError(f"Unsupported operator: {op}")

    def _apply_unop(self, op, val):
        if op == "not":
            return not val
        if op == "-":
            return -val
        raise EvaluationError(f"Unsupported unary operator: {op}")

    # ---------------------------------------------------------
    # Built-in dispatch (minimal)
    # ---------------------------------------------------------

    def _dispatch_function(self, fn, node, args):

        entity = self.model.entity_by_guid(node.guid)

        # IFC
        if fn == "ifc.type":
            return node.ifc_type

        if fn == "ifc.name":
            return self.model.get_name(entity)

        # PSET
        if fn == "pset.get":
            if len(args) != 2:
                return None
            return self.model.get_pset(entity, args[0], args[1])

        # Geometry
        if fn == "geom.bbox":
            return self.model.get_bbox(entity)

        if fn == "geom.exists":
            return self.model.has_geometry(entity)

        # Graph
        if fn == "degree":
            return self.graph.degree(node.guid)

        raise EvaluationError(f"Function not implemented in evaluator v0.2: {fn}")
