# pctx

A local-first CLI tool for indexing Markdown documentation into SQLite with full-text search (FTS5) and hierarchical navigation via stable section addresses.

Built for AI coding agents and developers who need fast, token-aware access to documentation repositories without loading entire files into context windows.

---

## Features

- **Local-first & Zero Cloud Dependencies**: Stores everything locally in `.pctx/index.sqlite`.
- **Hierarchical Section Addresses**: Deterministic, human-readable section pointers (`path/doc.md#heading/sub-heading`).
- **Full-Text Search (FTS5)**: Fast BM25 keyword search with 10x weighting for heading matches and contextual snippets.
- **Token Budgeting (`--max-tokens`)**: Truncates content cleanly at paragraph boundaries and provides continuation addresses.
- **Child Section Stubs (`--depth`)**: Inspect top-level sections with concise stubs pointing to deeper child sections.
- **Incremental Indexing**: Uses SHA-256 content hashes to re-index only added or modified files, automatically removing deleted documents.
- **Structured JSON Support (`--json`)**: First-class JSON output on every command for agent orchestration.

---

## Installation

```bash
# Editable install from repository root
pip install -e .

# Or using uv
uv pip install -e .
```

---

## Quick Start

```bash
# 1. Index documentation directory
pctx index ./docs

# 2. List all indexed documents with token estimates and summaries
pctx ls

# 3. View the heading hierarchy of a document
pctx outline docs/architecture.md

# 4. Show a specific section with depth-limited child stubs
pctx show docs/architecture.md#design --depth 1

# 5. Retrieve content capped by token budget
pctx show docs/architecture.md#design --max-tokens 500

# 6. Search documentation for keywords
pctx search "authentication"
```

---

## Command Reference

### `pctx index <root>`
Scans `<root>` recursively for `.md` files, parses their section trees, and updates `.pctx/index.sqlite`. Unchanged files are skipped based on SHA-256 hash.

```bash
pctx index ./docs
pctx index ./docs --json
```

### `pctx ls`
Lists all indexed documents along with estimated tokens and L0 summaries. Automatically discovers `.pctx/index.sqlite` by walking up the directory tree.

```bash
pctx ls
pctx ls --json
```

### `pctx outline <doc>`
Displays the heading hierarchy for the specified document with line ranges and token estimates.

```bash
pctx outline docs/guide.md
pctx outline docs/guide.md --depth 2
pctx outline docs/guide.md --json
```

### `pctx show <address>`
Retrieves Markdown content for a section address (e.g. `docs/guide.md#installation`) or an entire document (`docs/guide.md`).

- `--depth N`: Limits nested content expansion to $N$ levels; deeper child sections are rendered as child stubs.
- `--max-tokens N`: Enforces a token limit on the returned content, breaking cleanly at paragraph boundaries and appending continuation markers.
- `--json`: Returns structured JSON with section metadata, content, continuation addresses, and stubs.

```bash
pctx show docs/guide.md#installation
pctx show docs/guide.md#installation --depth 1 --max-tokens 1000
pctx show docs/guide.md#installation --json
```

### `pctx search "<query>"`
Performs BM25 ranked full-text search across indexed headings and body text. Headings are weighted 10x higher than body content.

```bash
pctx search "sqlite index"
pctx search "sqlite index" --json
```

---

## Section Addressing Scheme

Sections are identified by stable hierarchical addresses of the form:
`<file-path>#<parent-slug>/<child-slug>`

- **L0 Root**: `architecture.md` (the whole document)
- **H1 Section**: `architecture.md#overview`
- **H2 Subsection**: `architecture.md#overview/goals`
- **Duplicate Headings**: Sibling headings sharing the same text receive numeric suffixes:
  - `architecture.md#design/components`
  - `architecture.md#design/components-2`

---

## Token Estimation

Token counts are estimated using the deterministic formula:

$$\text{tokens} = \max\left(1, \lfloor \text{len}(\text{utf-8 bytes}) / 4 \rfloor\right)$$

This provides fast and consistent estimates across indexing and retrieval without requiring heavy tokenizer dependencies.

---

## Architecture

```
src/pctx/
├── __init__.py     # Package version
├── models.py       # Document and Section dataclasses
├── parser.py       # markdown-it-py tokenization, section tree, slug generation
├── index.py        # SQLite schema, transactions, FTS5 triggers, incremental hash checks
├── render.py       # Plain text and JSON renderers, token truncation, depth stubs
└── cli.py          # argparse CLI dispatch and exit codes
```

---

## License

MIT
