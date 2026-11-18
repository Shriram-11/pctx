# AGENTS.md

This file describes the PCTX project for AI coding agents.

## Project overview

`pctx` is a local-first Python CLI that indexes Markdown documentation into a SQLite FTS5 database and provides fast hierarchical navigation via stable section addresses.

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

## Section addresses

Sections are identified by stable addresses of the form `<file>#<slug>/<child-slug>`:

- Slugs are lowercase, punctuation-stripped, whitespace → hyphens
- Duplicate headings get a numeric suffix: `#section`, `#section-2`, `#section-3`
- The hierarchy is encoded with `/`: `architecture.md#design/components`

## Token estimation

```python
def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // 4)
```

## SQLite schema

See `index.py` for the full schema (`documents`, `sections`, `sections_fts`).
