# OpenBIM-DL Runtime

Reference CLI implementation of the OpenBIM Data Language (OpenBIM-DL).

This repository contains the executable engine that evaluates `.obimdl`
recipes against IFC (STEP) models and generates machine-learning-ready datasets.

---

## What is this?

OpenBIM-DL is a declarative language for transforming IFC semantic graphs
into reproducible AI training datasets.

This repository provides:

- A CLI runtime
- Parser and type checker
- IFC loader (IfcOpenShell-based)
- Semantic graph builder
- Expression evaluator
- Export engines (Parquet, JSON, GraphML)
- Manifest generation for reproducibility

Language specification lives here:

https://github.com/smanriquezfgithub/openbim-dl

---

## Status

⚠️ Early development (v0.2 runtime draft)

The language specification (v0.1) is stable.
The CLI implementation is under active development.

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

See:

`docs/architecture/runtime-v0.2-design.md`

---

## Installation (planned)

```bash
pip install openbimdl
