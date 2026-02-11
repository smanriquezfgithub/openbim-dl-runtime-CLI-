# openbimdl/ifc_loader.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.pset


class IFCModel:
    """
    Thin wrapper around IfcOpenShell providing:

    - Safe attribute access
    - Pset access
    - Quantity access
    - Type-based indexing
    - GlobalId indexing
    - Lightweight geometry helpers (bbox)

    This class does NOT:
    - build a semantic graph
    - evaluate OpenBIM-DL expressions
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

        if not self.path.exists():
            raise FileNotFoundError(f"IFC file not found: {self.path}")

        self._model = ifcopenshell.open(str(self.path))

        # index entities by GlobalId
        self._by_guid: Dict[str, Any] = {}
        self._by_type: Dict[str, List[Any]] = {}

        self._index_entities()

    # ---------------------------------------------------
    # Internal indexing
    # ---------------------------------------------------

    def _index_entities(self) -> None:
        for entity in self._model:
            # GlobalId
            guid = getattr(entity, "GlobalId", None)
            if guid:
                self._by_guid[guid] = entity

            # Type
            type_name = entity.is_a()
            self._by_type.setdefault(type_name, []).append(entity)

    # ---------------------------------------------------
    # Basic access
    # ---------------------------------------------------

    def raw(self):
        """Return raw IfcOpenShell model."""
        return self._model

    def schema(self) -> str:
        return self._model.schema

    def entity_by_guid(self, guid: str):
        return self._by_guid.get(guid)

    def entities_of_type(self, type_name: str) -> List[Any]:
        return self._by_type.get(type_name, [])

    def all_entities(self) -> List[Any]:
        return list(self._model)

    # ---------------------------------------------------
    # Attribute access
    # ---------------------------------------------------

    def get_attr(self, entity: Any, name: str) -> Any:
        """
        Safe attribute access.
        Returns None if attribute does not exist.
        """
        try:
            return getattr(entity, name)
        except AttributeError:
            return None

    def get_name(self, entity: Any) -> Optional[str]:
        return self.get_attr(entity, "Name")

    def get_predefined_type(self, entity: Any) -> Optional[str]:
        return self.get_attr(entity, "PredefinedType")

    # ---------------------------------------------------
    # Property sets
    # ---------------------------------------------------

    def get_psets(self, entity: Any) -> Dict[str, Dict[str, Any]]:
        """
        Return all property sets of an entity as a dict:
        {
            "Pset_WallCommon": {
                "LoadBearing": True,
                ...
            }
        }
        """
        try:
            return ifcopenshell.util.element.get_psets(entity)
        except Exception:
            return {}

    def get_pset(self, entity: Any, pset_name: str, prop_name: str) -> Any:
        psets = self.get_psets(entity)
        if pset_name in psets:
            return psets[pset_name].get(prop_name)
        return None

    def has_pset(self, entity: Any, pset_name: str) -> bool:
        psets = self.get_psets(entity)
        return pset_name in psets

    # ---------------------------------------------------
    # Quantities
    # ---------------------------------------------------

    def get_qtos(self, entity: Any) -> Dict[str, Dict[str, Any]]:
        try:
            return ifcopenshell.util.element.get_quantities(entity)
        except Exception:
            return {}

    def get_qto(self, entity: Any, qto_name: str, qty_name: str) -> Optional[float]:
        qtos = self.get_qtos(entity)
        if qto_name in qtos:
            return qtos[qto_name].get(qty_name)
        return None

    # ---------------------------------------------------
    # Lightweight geometry
    # ---------------------------------------------------

    def has_geometry(self, entity: Any) -> bool:
        try:
            return entity.Representation is not None
        except Exception:
            return False

    def get_bbox(self, entity: Any) -> Optional[List[float]]:
        """
        Return axis-aligned bounding box:
        [xmin, ymin, zmin, xmax, ymax, zmax]

        NOTE:
        - This uses IfcOpenShell's geometry module.
        - It is lightweight but may fail for malformed geometry.
        """
        try:
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)

            shape = ifcopenshell.geom.create_shape(settings, entity)
            verts = shape.geometry.verts

            xs = verts[0::3]
            ys = verts[1::3]
            zs = verts[2::3]

            return [
                min(xs),
                min(ys),
                min(zs),
                max(xs),
                max(ys),
                max(zs),
            ]
        except Exception:
            return None

    # ---------------------------------------------------
    # Debug helpers
    # ---------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "schema": self.schema(),
            "total_entities": len(self._model),
            "types": len(self._by_type),
        }
