# Bug Fix: Heading IDs Leak into Addresses

## Problem

About half the headings in real-world Markdown corpora (e.g. FastAPI docs) use the `{ #custom-id }` syntax to define explicit anchor IDs. The parser's `slugify` function doesn't recognize this syntax and slugifies the entire heading text including the attribute block, producing bloated, duplicated addresses like:

```
cors-cross-origin-resource-sharing-cors-cross-origin-resource-sharing
```

Median address length is 62 characters, maximum 399 — far longer than necessary and confusing for agents to work with.

### Root cause

[`parser.py` line 110–136](file:///c:/Users/nshri/Github/pctx/src/pctx/parser.py#L110-L136): `_extract_headings` reads the raw inline content from markdown-it tokens, which includes the `{ #id }` attribute block as literal text. The `slugify` function then processes the entire string, treating `{ #custom-id }` as regular heading text.

The `{ #id }` syntax comes from the `attr` extension (also known as "header attributes" in Python-Markdown, or the `attrs` plugin in `mdit-py-plugins`). `mdit-py-plugins` is already a declared dependency of pctx, but `parser.py` only imports the base `markdown_it.MarkdownIt` — it never enables the `attrs` plugin.

## Fix

### Step 1: Extract explicit IDs from heading text

Before slugifying, check if the heading text ends with `{ #some-id }`. If it does, use `some-id` as the slug directly and strip the attribute block from the displayed heading text.

**In `parser.py`**, add a helper:

```python
import re

# Matches { #some-id } at the end of a heading, with optional other attrs
_HEADING_ID_RE = re.compile(r'\s*\{[^}]*#([a-zA-Z0-9_-]+)[^}]*\}\s*$')

def _extract_heading_id(text: str) -> tuple[str, str | None]:
    """Extract explicit heading ID from { #id } attribute syntax.
    
    Returns (clean_heading_text, explicit_id_or_None).
    """
    m = _HEADING_ID_RE.search(text)
    if m:
        explicit_id = m.group(1)
        clean_text = text[:m.start()].strip()
        return clean_text, explicit_id
    return text, None
```

### Step 2: Use the explicit ID in `_build_sections`

**In `_build_sections`**, before calling `slugify`, check for an explicit ID:

```python
# Current (line 239):
raw_slug = slugify(h.text)

# Proposed:
clean_text, explicit_id = _extract_heading_id(h.text)
if explicit_id:
    raw_slug = explicit_id
    h.text = clean_text  # Update heading text to strip the { #id } block
else:
    raw_slug = slugify(h.text)
```

This means:
- Headings with `{ #custom-id }` use `custom-id` as the slug.
- Headings without explicit IDs continue using the existing `slugify` logic.
- The heading text stored in the Section object is cleaned (no `{ #id }` block).

### Step 3: Also clean heading text in `_extract_headings`

The heading text should be cleaned at extraction time so that the `Section.heading` field never contains the raw `{ #id }` attribute block:

```python
# In _extract_headings, after getting heading_text:
heading_text = tokens[i + 1].content.strip()

# Add:
clean_text, _ = _extract_heading_id(heading_text)
heading_text = clean_text
```

But we still need the explicit ID later in `_build_sections`. Two options:

**Option A (simpler):** Extract the ID in `_build_sections` from the original text, then clean. Store the original text in `_Heading.text` and clean it only when building the Section.

**Option B:** Add an `explicit_id` field to `_Heading` and populate it during extraction.

> [!TIP]
> **Recommended: Option B.** It's cleaner — extraction happens once, and `_build_sections` just reads `h.explicit_id`.

```python
class _Heading:
    __slots__ = ('level', 'text', 'line', 'explicit_id')

    def __init__(self, level: int, text: str, line: int, explicit_id: str | None = None) -> None:
        self.level = level
        self.text = text
        self.line = line
        self.explicit_id = explicit_id
```

In `_extract_headings`:

```python
heading_text = tokens[i + 1].content.strip()
clean_text, explicit_id = _extract_heading_id(heading_text)
headings.append(_Heading(level, clean_text, line, explicit_id))
```

In `_build_sections`:

```python
raw_slug = h.explicit_id if h.explicit_id else slugify(h.text)
```

### Step 4: Add a parser version to the content hash

The roadmap notes: "Add a parser version to the content hash, otherwise unchanged files keep their old addresses after the fix."

When we change how slugs are computed, files that haven't changed on disk still need re-indexing because their section addresses are now different.

**In `index.py`**, add a parser version constant and include it in the content hash:

```python
# At module level:
PARSER_VERSION = "2"  # Bump when slug/address computation changes

# In _sha256 or index_file:
def _content_hash(text: str) -> str:
    """Hash content + parser version so address changes force re-indexing."""
    return hashlib.sha256(f"v{PARSER_VERSION}\n{text}".encode("utf-8")).hexdigest()
```

Replace `_sha256(content)` calls with `_content_hash(content)` in `index_file`.

> [!WARNING]
> This will cause a full re-index on the next `pctx index` run for every file, since all hashes will change. This is intentional — the old addresses are wrong and must be replaced.

## Files to change

| File | Change |
| --- | --- |
| [`src/pctx/parser.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/parser.py) | Add `_HEADING_ID_RE`, `_extract_heading_id`; update `_Heading`, `_extract_headings`, `_build_sections` |
| [`src/pctx/index.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/index.py) | Add `PARSER_VERSION`; update content hash to include it |
| [`tests/test_parser.py`](file:///c:/Users/nshri/Github/pctx/tests/test_parser.py) | Add tests for explicit heading IDs |
| [`tests/fixtures/`](file:///c:/Users/nshri/Github/pctx/tests/fixtures/) | Add a fixture with `{ #id }` headings |

## Tests to add

### New fixture: `tests/fixtures/heading-ids.md`

```markdown
# Introduction

Basic intro.

## Getting Started { #getting-started }

Setup instructions.

### Installation { #install }

Install steps.

## CORS (Cross-Origin Resource Sharing) { #cors }

CORS configuration.

## No Explicit ID

This heading uses the default slug.
```

### Test cases

1. **`test_explicit_id_used_as_slug`** — Parse `heading-ids.md`. The section for "Getting Started" should have slug `getting-started`, not `getting-started-getting-started`.
2. **`test_explicit_id_short_slug`** — The section for "Installation" should have slug `install`, not `installation-install`.
3. **`test_explicit_id_cors`** — The section for "CORS" should have slug `cors`, not `cors-cross-origin-resource-sharing-cors`.
4. **`test_no_explicit_id_unchanged`** — The section for "No Explicit ID" should use the normal slugify result: `no-explicit-id`.
5. **`test_heading_text_cleaned`** — `Section.heading` for the "Getting Started" section should be `"Getting Started"`, not `"Getting Started { #getting-started }"`.
6. **`test_address_uses_explicit_id`** — Full address should be `heading-ids.md#getting-started`, not the bloated version.
7. **`test_nested_explicit_id`** — Address for "Installation" should be `heading-ids.md#getting-started/install`.
8. **`test_parser_version_forces_reindex`** — After bumping `PARSER_VERSION`, a previously-unchanged file should be re-indexed.

## Verification

```bash
# After fix:
pytest tests/test_parser.py -v -k "heading_id or explicit_id"

# Full suite must pass:
pytest tests/ -v

# Manual check on a real corpus with { #id } headings:
pctx index ./docs
pctx outline some-doc.md   # Addresses should be short and clean
```

## Risk

- **Medium risk.** This changes address generation, which is a core behavior. All existing addresses for documents with `{ #id }` headings will change. Any saved/cached addresses become stale.
- **Mitigated by:** The parser version bump forces a full re-index, so the index will be consistent after the next `pctx index` run.
- **Existing documents without `{ #id }` are unaffected** — their slugs are computed the same way as before.
