# pctx

**pctx** is a local-first Python CLI tool for indexing and navigating Markdown documentation.

## Installation

```bash
uv pip install -e .
```

## Usage

```bash
pctx index ./docs          # Build or update the index
pctx ls                    # List indexed documents
pctx outline path/doc.md   # Display document heading hierarchy
pctx show path/doc.md#section  # Retrieve section content
pctx search "query"        # Search indexed content
```

## Common options

- `--json` — Output as JSON (all commands)
- `--depth N` — Limit section depth (show)
- `--max-tokens N` — Token budget for output (show)

## Development

```bash
uv pip install -e ".[dev]"
pytest
```
