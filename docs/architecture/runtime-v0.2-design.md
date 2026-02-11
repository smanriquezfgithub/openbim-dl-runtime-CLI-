# OpenBIM-DL Runtime v0.2 — Architecture Design

## 1. Overview

This document defines the architecture of the reference CLI implementation
of the OpenBIM Data Language (OpenBIM-DL).

OpenBIM-DL is a declarative language for transforming IFC semantic graphs
into machine-learning-ready datasets.

The runtime is responsible for:

1. Parsing `.obimdl` recipes
2. Type checking
3. Loading IFC (STEP)
4. Building a semantic graph
5. Evaluating expressions
6. Exporting datasets
7. Generating a reproducible manifest

This document describes the internal architecture of the CLI runtime (v0.2).

---

## 2. Design Principles

### Determinism
Given:
- same IFC input
- same recipe
- same runtime version
- same seed (if synthesize is used)

The outputs must be identical.

### Separation of Concerns

The runtime is divided into clearly separated components:

- Parser
- AST
- Type Checker
- IFC Loader
- Graph Builder
- Expression Evaluator
- Export Engines
- Manifest Generator

No component should depend on higher-level logic.

### Reproducibility

Each run produces a manifest containing:

- runtime version
- recipe hash
- IFC fingerprint
- configuration
- output hashes
- execution metadata

---

## 3. Execution Pipeline

The runtime follows a staged execution model:

1. Parse recipe → AST
2. Type check → Typed AST
3. Load IFC
4. Build semantic graph
5. Evaluate derive/synthesize/split blocks
6. Export outputs
7. Generate manifest

Each stage produces a well-defined intermediate representation.

---

## 4. Core Components

### 4.1 Parser

Responsibility:
- Convert recipe text into a parse tree.

Technology:
- Python + Lark

Output:
- Parse tree

---

### 4.2 AST Builder

Responsibility:
- Transform parse tree into structured AST objects.

Output:
- AST

---

### 4.3 Type Checker

Responsibility:
- Validate block structure
- Validate function calls
- Enforce type rules

Output:
- Typed AST

---

### 4.4 IFC Loader

Responsibility:
- Load IFC model
- Provide attribute/property access

Technology:
- IfcOpenShell (Python)

---

### 4.5 Graph Builder

Responsibility:
- Project IFC entities into semantic graph:
  - Nodes
  - Typed edges
  - Indexed relationships

Graph is held in memory for fast traversal.

---

### 4.6 Expression Evaluator

Responsibility:
- Evaluate expressions in:
  - Node context
  - Edge context
  - Batch context

Handles:
- Null propagation
- Built-in function dispatch
- Context switching

---

### 4.7 Export Engines

Supported formats (v0.2):

- Parquet (PyArrow)
- JSON / JSONL
- Edge list
- GraphML

Each export is deterministic and schema-aware.

---

### 4.8 Manifest Generator

Responsibility:
- Record execution metadata
- Ensure auditability
- Enable reproducibility

Manifest is written as JSON.

---

## 5. CLI Interface

Planned commands:

openbimdl run model.ifc recipe.obimdl --out ./out
openbimdl validate recipe.obimdl
openbimdl explain recipe.obimdl


---

## 6. Future Evolution

v0.3 may introduce:

- Performance optimization
- Rust hot-path components
- Plugin-based geometry engines
- Parallel evaluation
- Web runtime

---

## 7. Repository Structure

openbim-dl-runtime/
docs/
architecture/
runtime-v0.2-design.md
diagrams/
openbimdl/
tests/
pyproject.toml


---

This architecture establishes the reference implementation of OpenBIM-DL.
