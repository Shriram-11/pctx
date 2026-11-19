# Changelog

All notable changes to the `pctx` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-11-19

### Added

#### Core Architecture & Domain Models
- Created `Document` and `Section` dataclasses in [`src/pctx/models.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/models.py) providing typed data contracts across parser, database, and rendering layers.

#### Markdown Parser Engine
- Implemented [`src/pctx/parser.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/parser.py) using `markdown-it-py` for CommonMark tokenization.
- Support for ATX (`#`) and Setext (`===`, `---`) heading hierarchies.
- Strict code block isolation preventing Python/Bash `#` comments inside fenced blocks from triggering false headings.
- Front matter stripping with line-offset tracking to preserve byte-exact line ranges matching source files on disk.
- Deterministic slugification and sibling duplicate disambiguation (`overview`, `overview-2`).
- Uniform token estimation formula: $\max(1, \lfloor \text{bytes} / 4 \rfloor)$.

#### SQLite Indexing & Storage
- Implemented [`src/pctx/index.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/index.py) managing `.pctx/index.sqlite` with WAL mode and foreign key constraints.
- Content-addressed incremental indexing using SHA-256 hashes to skip unchanged files and purge deleted files.
- Atomic file upserts ensuring failed indexing or parse errors roll back cleanly without leaving partial records.
- SQLite FTS5 virtual table (`sections_fts`) kept synchronized via automatic SQL database triggers (`AFTER INSERT`, `AFTER DELETE`, `AFTER UPDATE`).
- BM25 full-text search with 10x column weighting for heading matches over body text, accompanied by contextual snippet generation.
- Dynamic index discovery (`Index.find`) that walks up directory trees to locate the nearest `.pctx/index.sqlite`.

#### Presentation & Budgeting
- Implemented [`src/pctx/render.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/render.py) supporting both human-readable plain text and structured JSON formats.
- Hierarchical token truncation (`--max-tokens`) that breaks on paragraph boundaries, falling back to line boundaries, and appends explicit continuation addresses (`[TRUNCATED]\nContinue from: <address>`).
- Child subsection stubbing (`--depth`) that replaces deeper nested content with concise subsection navigation pointers.

#### CLI Dispatcher
- Implemented [`src/pctx/cli.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/cli.py) with five core subcommands:
  - `pctx index <root> [--json]`
  - `pctx ls [--json]`
  - `pctx outline <doc> [--depth N] [--json]`
  - `pctx show <address> [--depth N] [--max-tokens N] [--json]`
  - `pctx search "<query>" [--json]`
- Strict stream discipline routing clean command output to `stdout` and diagnostic logs/errors to `stderr`.

#### Documentation & Test Suite
- Comprehensive test suite with 98 unit and integration tests across `test_parser.py`, `test_index.py`, `test_render.py`, `test_cli.py`, and `test_search.py`.
- Documentation suite under [`docs/`](file:///c:/Users/nshri/Github/pctx/docs/):
  - [`docs/architecture.md`](file:///c:/Users/nshri/Github/pctx/docs/architecture.md)
  - [`docs/models.md`](file:///c:/Users/nshri/Github/pctx/docs/models.md)
  - [`docs/parser.md`](file:///c:/Users/nshri/Github/pctx/docs/parser.md)
  - [`docs/index.md`](file:///c:/Users/nshri/Github/pctx/docs/index.md)
  - [`docs/render.md`](file:///c:/Users/nshri/Github/pctx/docs/render.md)
  - [`docs/cli.md`](file:///c:/Users/nshri/Github/pctx/docs/cli.md)
- Standard AI agent navigation workflow in [`AGENTS.md`](file:///c:/Users/nshri/Github/pctx/AGENTS.md).
