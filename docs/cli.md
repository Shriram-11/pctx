# PCTX CLI Layer (`src/pctx/cli.py`)

[`src/pctx/cli.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/cli.py) is the entry point for the `pctx` command-line interface. It defines argument parsers, manages index discovery, and coordinates data flow between the index engine and the renderers.

---

## Design Principles

### 1. Strict Stream Discipline
- **`stdout`**: Reserved exclusively for command output (plain text or machine-readable JSON). No progress logs, informational banners, or diagnostics are ever sent to `stdout`.
- **`stderr`**: Used for progress reports (e.g. `Indexed docs: 8 added, 0 updated`), warnings, and error messages.

This guarantees that an AI agent or shell pipeline running `pctx ls --json | jq .` will never fail due to unexpected progress messages.

### 2. Standard Exit Codes
- **`0`**: Command completed successfully.
- **`1`**: Runtime error (e.g. `.pctx/index.sqlite` not found, section not found in index, target directory does not exist).
- **`2`**: Command-line syntax error (invalid flags, missing arguments handled by `argparse`).

---

## Subcommand Reference

```
pctx [-h] {index,ls,outline,show,search} ...
```

### 1. `pctx index <root> [--json]`
Builds or updates the SQLite index for the specified directory.

- **Arguments**:
  - `root`: Root directory containing Markdown files to index.
  - `--json`: (Optional) Outputs the indexing statistics dictionary as JSON.
- **Behavior**:
  - Automatically creates `.pctx/index.sqlite` inside `<root>`.
  - Scans for all `.md` files, skipping hidden files/directories.
  - Uses SHA-256 hashes to skip unchanged files.
  - Emits stats (`added`, `updated`, `unchanged`, `deleted`) to `stderr` (or `stdout` if `--json`).

### 2. `pctx ls [--json]`
Lists all indexed documents along with estimated tokens and L0 summaries.

- **Arguments**:
  - `--json`: (Optional) Emits JSON array of document objects.
- **Behavior**:
  - Automatically discovers the index by walking up from the current directory.
  - If no index is found, prints an actionable error to `stderr` and exits with code `1`.

### 3. `pctx outline <document> [--depth N] [--json]`
Displays the heading hierarchy for a specific document.

- **Arguments**:
  - `document`: Path to the document (e.g. `README.md` or `docs/guide.md`). Any section fragment (e.g. `#overview`) is automatically stripped.
  - `--depth N`: (Optional) Limits headings displayed to maximum level $N$.
  - `--json`: (Optional) Emits JSON array of heading metadata.

### 4. `pctx show <address> [--depth N] [--max-tokens N] [--json]`
Retrieves Markdown content for a section address or whole document.

- **Arguments**:
  - `address`: Stable section address (e.g. `docs/guide.md#installation`) or document path (e.g. `docs/guide.md`).
  - `--depth N`: (Optional) Limits child subsection expansion; deeper subsections are rendered as concise child stubs.
  - `--max-tokens N`: (Optional) Caps output tokens, cleanly truncating at paragraph boundaries and appending continuation markers.
  - `--json`: (Optional) Emits structured JSON with section metadata, content, continuation addresses, and stubs.

### 5. `pctx search "<query>" [--json]`
Executes a BM25 ranked full-text search across indexed headings and body text.

- **Arguments**:
  - `query`: Search terms (e.g. `"sqlite index"` or `"authentication"`).
  - `--json`: (Optional) Emits JSON array of search match objects with snippets and scores.

---

## Error Handling Scenarios

| Error Condition | Behavior | Exit Code |
|---|---|---|
| Unindexed directory (`pctx ls`) | Prints `Error: No pctx index found starting from '...'. Run 'pctx index <root>' first.` to `stderr`. | `1` |
| Missing section (`pctx show doc.md#missing`) | Prints `Error: Section 'doc.md#missing' not found in index.` to `stderr`. | `1` |
| Missing document (`pctx outline missing.md`) | Prints `Error: Document 'missing.md' not found in index.` to `stderr`. | `1` |
| Invalid directory (`pctx index /nonexistent`) | Prints `Error: Directory '/nonexistent' does not exist.` to `stderr`. | `1` |
| Malformed search query (e.g. unclosed quotes) | Query is sanitized automatically; returns empty list if no valid terms remain without crashing. | `0` |
