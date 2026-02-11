# OpenBIM-DL Runtime (CLI)

Reference CLI implementation of the **OpenBIM Data Language (OpenBIM-DL)**.

This repository contains the **executable engine** that evaluates `.obimdl`
recipes against IFC (STEP) models and generates **machine-learning-ready datasets**.

**Language specification (v0.1) lives here:**
- https://github.com/smanriquezfgithub/openbim-dl

---

## What is OpenBIM-DL?

OpenBIM-DL is a **declarative, graph-first language** for transforming IFC building models
into reproducible AI datasets (tabular, graph, text).

This runtime provides the machinery to:

1. Load an IFC model (IfcOpenShell)
2. Build a semantic graph (nodes + normalized edges)
3. Execute a recipe (view + derive)
4. Export datasets
5. Generate a reproducibility manifest

---

## Status

⚠️ **Early development (runtime v0.2.0 — pre-alpha)**

Implemented in v0.2.0:
- CLI commands: `version`, `validate`, `explain`, `run`
- Parser + AST builder
- Minimal type checker
- IFC loader (IfcOpenShell wrapper)
- Semantic graph builder (subset):
  - `contained_in`
  - `aggregates`
  - `type_of`
  - `connects_to` (best-effort)
- Minimal evaluator:
  - `view.select`, `view.where`
  - `derive.feature`
  - small set of built-ins (`ifc.type`, `ifc.name`, `pset.get`, `geom.exists`, `geom.bbox`, `degree`)
- Export engines:
  - Tabular: Parquet, JSONL
  - Graph: edge list (TSV)
- Manifest generation (`manifest.json`)

Not implemented yet (planned):
- `synthesize` execution (noise, missingness, balancing)
- `split` execution (anti-leakage partitions)
- full built-in catalog coverage (Chapter 4)
- performance optimizations + caching

---

## Architecture Overview

OpenBIM-DL Runtime follows a staged execution model:

1. Parse `.obimdl` recipe
2. Build AST
3. Type check
4. Load IFC model
5. Build semantic graph
6. Evaluate expressions
7. Export datasets
8. Generate manifest

Design doc:
- `docs/architecture/runtime-v0.2-design.md`

---

## Installation

> Note: `ifcopenshell` availability depends on OS/Python version.
> If `pip` fails, you may need a prebuilt wheel or conda-based install.

Create a virtual environment and install in editable mode:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -U pip
pip install -e .
