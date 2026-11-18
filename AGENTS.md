# AGENTS.md

This file describes the PCTX project and instructions for AI coding agents.

## Project overview

`pctx` is a local-first Python CLI that indexes Markdown documentation into a SQLite FTS5 database and provides fast hierarchical navigation via stable section addresses.

---

## Agent Navigation Workflow

When exploring or retrieving information from a documentation repository, **always prefer `pctx` over reading entire Markdown files directly.** Reading entire files wastes context window tokens and introduces irrelevant noise.

Follow this standard 5-step navigation workflow:

### Step 1: Discover documents
List available documentation and their L0 summaries:
```bash
pctx ls --json
```

### Step 2: Inspect document structure
Before fetching the full content of an unfamiliar document, inspect its outline:
```bash
pctx outline path/to/document.md --json
```
Use `--depth 1` or `--depth 2` for very large documents to view top-level structure first.

### Step 3: Retrieve relevant sections
Fetch only the specific section needed for your task, applying a token budget and depth limit:
```bash
pctx show path/to/document.md#section-slug --depth 1 --max-tokens 2000 --json
```

### Step 4: Follow continuation addresses
If the response contains `"truncated": true`, use the `continuation_address` (or `Continue from: <address>` marker in text mode) to retrieve the next chunk:
```bash
pctx show <continuation_address> --max-tokens 2000
```

### Step 5: Search when you don't know where to look
If you do not know which document contains the answer, perform a full-text search:
```bash
pctx search "authentication middleware" --json
```

---

## Section addresses

Sections are identified by stable addresses of the form `<file>#<slug>/<child-slug>`:

- Slugs are lowercase, punctuation-stripped, whitespace → hyphens
- Duplicate headings get a numeric suffix: `#section`, `#section-2`, `#section-3`
- The hierarchy is encoded with `/`: `architecture.md#design/components`
- The root document address is the file path itself: `architecture.md`

---

## Token estimation

```python
def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // 4)
```

---

## Repository layout

```
pctx/
├── pyproject.toml          # Project metadata and build config
├── README.md
├── AGENTS.md               # This file
├── src/
│   └── pctx/
│       ├── __init__.py     # Package version
│       ├── cli.py          # argparse entry point → main()
│       ├── parser.py       # Markdown → Section tree
│       ├── index.py        # SQLite + FTS5 index management
│       ├── render.py       # Text / JSON renderers
│       └── models.py       # Document and Section dataclasses
└── tests/
    ├── fixtures/           # Markdown test documents
    ├── test_parser.py
    ├── test_index.py
    ├── test_cli.py
    ├── test_search.py
    └── test_render.py
```
