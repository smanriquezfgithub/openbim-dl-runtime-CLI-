# openbimdl/graph.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from openbimdl.ifc_loader import IFCModel


# -----------------------------
# Core graph data structures
# -----------------------------

EdgeKind = str


@dataclass(frozen=True)
class NodeRef:
    guid: str
    ifc_type: str


@dataclass(frozen=True)
class EdgeRef:
    source: str  # guid
    target: str  # guid
    kind: EdgeKind


class SemanticGraph:
    """
    In-memory semantic graph for IFC.

    Nodes:
      - identified by GlobalId (GUID)
    Edges (subset):
      - contained_in
      - aggregates
      - type_of
      - connects_to

    This graph is used by the evaluator to implement OpenBIM-DL built-ins.
    """

    def __init__(self, model: IFCModel, rel_whitelist: Optional[List[str]] = None):
        self.model = model
        self.rel_whitelist = set(rel_whitelist) if rel_whitelist else None

        # Node indices
        self._nodes: Dict[str, NodeRef] = {}            # guid -> NodeRef
        self._by_type: Dict[str, List[str]] = {}        # ifc_type -> [guid]

        # Edge indices
        self._out: Dict[str, List[EdgeRef]] = {}        # guid -> outgoing edges
        self._in: Dict[str, List[EdgeRef]] = {}         # guid -> incoming edges

        self._build()

    # -------------------------
    # Public API
    # -------------------------

    def nodes(self) -> List[NodeRef]:
        return list(self._nodes.values())

    def node(self, guid: str) -> Optional[NodeRef]:
        return self._nodes.get(guid)

    def nodes_of_type(self, ifc_type: str) -> List[NodeRef]:
        guids = self._by_type.get(ifc_type, [])
        return [self._nodes[g] for g in guids if g in self._nodes]

    def out_edges(self, guid: str, kind: Optional[str] = None) -> List[EdgeRef]:
        edges = self._out.get(guid, [])
        if kind is None:
            return edges
        return [e for e in edges if e.kind == kind]

    def in_edges(self, guid: str, kind: Optional[str] = None) -> List[EdgeRef]:
        edges = self._in.get(guid, [])
        if kind is None:
            return edges
        return [e for e in edges if e.kind == kind]

    def neighbors(self, guid: str, kind: Optional[str] = None) -> List[NodeRef]:
        neigh = []
        for e in self.out_edges(guid, kind=kind):
            n = self.node(e.target)
            if n:
                neigh.append(n)
        for e in self.in_edges(guid, kind=kind):
            n = self.node(e.source)
            if n:
                neigh.append(n)
        # Dedup by guid while preserving order
        seen: Set[str] = set()
        out: List[NodeRef] = []
        for n in neigh:
            if n.guid not in seen:
                seen.add(n.guid)
                out.append(n)
        return out

    def contained_in(self, guid: str) -> Optional[NodeRef]:
        """
        Return the immediate spatial container for an element.
        """
        # outgoing edge: element -> container
        edges = self.out_edges(guid, kind="contained_in")
        if not edges:
            return None
        return self.node(edges[0].target)

    def container_chain(self, guid: str) -> List[NodeRef]:
        """
        Return a chain element -> storey -> building -> site (best-effort).
        """
        out: List[NodeRef] = []
        current = guid
        visited: Set[str] = set()
        while True:
            if current in visited:
                break
            visited.add(current)

            parent = self.contained_in(current)
            if not parent:
                break
            out.append(parent)
            current = parent.guid
        return out

    def connects_to(self, guid: str) -> List[NodeRef]:
        """
        Return nodes connected via connects_to edges.
        """
        return self.neighbors(guid, kind="connects_to")

    def aggregates(self, guid: str) -> List[NodeRef]:
        """
        Return parts aggregated by this node (outgoing aggregates edges).
        """
        return [self.node(e.target) for e in self.out_edges(guid, kind="aggregates") if self.node(e.target)]

    def decomposes(self, guid: str) -> Optional[NodeRef]:
        """
        Return parent in decomposition (incoming aggregates edge).
        """
        edges = self.in_edges(guid, kind="aggregates")
        if not edges:
            return None
        return self.node(edges[0].source)

    def type_of(self, guid: str) -> Optional[NodeRef]:
        """
        Return Type object associated to this instance (outgoing type_of edge).
        """
        edges = self.out_edges(guid, kind="type_of")
        if not edges:
            return None
        return self.node(edges[0].target)

    def degree(self, guid: str, kind: Optional[str] = None) -> int:
        if kind is None:
            return len(self._out.get(guid, [])) + len(self._in.get(guid, []))
        return len(self.out_edges(guid, kind=kind)) + len(self.in_edges(guid, kind=kind))

    # -------------------------
    # Build graph
    # -------------------------

    def _build(self) -> None:
        self._index_nodes()
        self._build_edges_contained_in()
        self._build_edges_aggregates()
        self._build_edges_type_of()
        self._build_edges_connects_to()

    def _allow(self, kind: str) -> bool:
        if self.rel_whitelist is None:
            return True
        return kind in self.rel_whitelist

    def _add_node(self, guid: str, ifc_type: str) -> None:
        if not guid:
            return
        if guid in self._nodes:
            return
        self._nodes[guid] = NodeRef(guid=guid, ifc_type=ifc_type)
        self._by_type.setdefault(ifc_type, []).append(guid)

    def _add_edge(self, source_guid: str, target_guid: str, kind: str) -> None:
        if not source_guid or not target_guid:
            return
        if source_guid not in self._nodes or target_guid not in self._nodes:
            return
        e = EdgeRef(source=source_guid, target=target_guid, kind=kind)
        self._out.setdefault(source_guid, []).append(e)
        self._in.setdefault(target_guid, []).append(e)

    def _index_nodes(self) -> None:
        """
        Add all entities with a GlobalId as nodes.
        """
        for ent in self.model.all_entities():
            guid = getattr(ent, "GlobalId", None)
            if guid:
                self._add_node(guid=guid, ifc_type=ent.is_a())

    # -------------------------
    # Edge builders
    # -------------------------

    def _build_edges_contained_in(self) -> None:
        """
        Build 'contained_in' edges using IfcRelContainedInSpatialStructure:
          element -> spatial container
        """
        if not self._allow("contained_in"):
            return

        rels = self.model.raw().by_type("IfcRelContainedInSpatialStructure")
        for r in rels:
            structure = getattr(r, "RelatingStructure", None)
            related = getattr(r, "RelatedElements", None)
            if not structure or not related:
                continue

            container_guid = getattr(structure, "GlobalId", None)
            if not container_guid:
                continue

            for el in related:
                el_guid = getattr(el, "GlobalId", None)
                if el_guid:
                    self._add_edge(el_guid, container_guid, "contained_in")

    def _build_edges_aggregates(self) -> None:
        """
        Build 'aggregates' edges using IfcRelAggregates:
          whole -> part
        """
        if not self._allow("aggregates"):
            return

        rels = self.model.raw().by_type("IfcRelAggregates")
        for r in rels:
            whole = getattr(r, "RelatingObject", None)
            parts = getattr(r, "RelatedObjects", None)
            if not whole or not parts:
                continue

            whole_guid = getattr(whole, "GlobalId", None)
            if not whole_guid:
                continue

            for p in parts:
                part_guid = getattr(p, "GlobalId", None)
                if part_guid:
                    self._add_edge(whole_guid, part_guid, "aggregates")

    def _build_edges_type_of(self) -> None:
        """
        Build 'type_of' edges using IfcRelDefinesByType:
          instance -> type
        """
        if not self._allow("type_of"):
            return

        rels = self.model.raw().by_type("IfcRelDefinesByType")
        for r in rels:
            typ = getattr(r, "RelatingType", None)
            related = getattr(r, "RelatedObjects", None)
            if not typ or not related:
                continue

            type_guid = getattr(typ, "GlobalId", None)
            if not type_guid:
                continue

            for obj in related:
                obj_guid = getattr(obj, "GlobalId", None)
                if obj_guid:
                    self._add_edge(obj_guid, type_guid, "type_of")

    def _build_edges_connects_to(self) -> None:
        """
        Build 'connects_to' edges (best-effort) using multiple IFC relationship patterns.

        Primary:
          IfcRelConnectsElements (RelatingElement -> RelatedElement)
        Secondary (MEP):
          IfcRelConnectsPorts (RelatingPort -> RelatedPort)
          IfcRelConnectsPortToElement (RelatingPort -> RelatedElement)
        """
        if not self._allow("connects_to"):
            return

        # 1) IfcRelConnectsElements
        for r in self.model.raw().by_type("IfcRelConnectsElements"):
            a = getattr(r, "RelatingElement", None)
            b = getattr(r, "RelatedElement", None)
            if not a or not b:
                continue
            ga = getattr(a, "GlobalId", None)
            gb = getattr(b, "GlobalId", None)
            if ga and gb:
                self._add_edge(ga, gb, "connects_to")

        # 2) IfcRelConnectsPorts (port->port)
        for r in self.model.raw().by_type("IfcRelConnectsPorts"):
            a = getattr(r, "RelatingPort", None)
            b = getattr(r, "RelatedPort", None)
            if not a or not b:
                continue
            ga = getattr(a, "GlobalId", None)
            gb = getattr(b, "GlobalId", None)
            if ga and gb:
                self._add_edge(ga, gb, "connects_to")

        # 3) IfcRelConnectsPortToElement (port->element)
        for r in self.model.raw().by_type("IfcRelConnectsPortToElement"):
            port = getattr(r, "RelatingPort", None)
            el = getattr(r, "RelatedElement", None)
            if not port or not el:
                continue
            gp = getattr(port, "GlobalId", None)
            ge = getattr(el, "GlobalId", None)
            if gp and ge:
                self._add_edge(gp, ge, "connects_to")

    # -------------------------
    # Export helpers (for GNN etc.)
    # -------------------------

    def edge_list(self, kinds: Optional[List[str]] = None) -> List[Tuple[str, str, str]]:
        """
        Return list of (source_guid, target_guid, edge_kind).
        If kinds is provided, filter by those kinds.
        """
        kinds_set = set(kinds) if kinds else None
        out: List[Tuple[str, str, str]] = []
        for src, edges in self._out.items():
            for e in edges:
                if kinds_set is None or e.kind in kinds_set:
                    out.append((e.source, e.target, e.kind))
        return out

    def kinds(self) -> List[str]:
        """
        Return distinct edge kinds present.
        """
        ks: Set[str] = set()
        for edges in self._out.values():
            for e in edges:
                ks.add(e.kind)
        return sorted(ks)

    def stats(self) -> Dict[str, Any]:
        return {
            "nodes": len(self._nodes),
            "edge_kinds": self.kinds(),
            "edges_total": sum(len(v) for v in self._out.values()),
        }
