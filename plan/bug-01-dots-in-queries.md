# Bug Fix: Dots in Queries Return Nothing

## Problem

Searching for terms containing dots — `0.100.0`, `app.mount`, `main.py` — returns zero results. The query sanitizer in `index.py` strips every character that isn't alphanumeric, `-`, or `_`, so `0.100.0` becomes three separate tokens `0`, `100`, `0`, but each is under the minimum length of 2 and gets dropped. Even when tokens survive (e.g. `app` and `mount` from `app.mount`), the original dotted term is lost as a phrase.

### Root cause

[`_execute_search`](file:///c:/Users/nshri/Github/pctx/src/pctx/index.py#L477-L562) at line 496:

```python
clean_term = "".join(c for c in term if c.isalnum() or c in ("-", "_"))
```

This strips dots unconditionally. FTS5's default tokenizer (`unicode61`) already splits on dots during indexing, so the indexed content has tokens like `0`, `100`, `app`, `mount`. But the query sanitizer also drops short tokens (len < 2 via `_tokenize_terms`) and doesn't preserve the relationship between the parts.

The deeper issue is that FTS5 itself tokenizes `0.100.0` into `0`, `100`, `0` during indexing. So even with a perfect query, `"0"` is too common and `"100"` alone is ambiguous. The user needs a **phrase query** — `"0" "100" "0"` as a NEAR or phrase — to match the original dotted string.

## Fix

### Step 1: Preserve dots in query terms and pass them to FTS5 as phrases

Replace the current sanitizer with one that:

1. Keeps dots within terms (so `0.100.0` stays as one token).
2. Splits the dotted term into its FTS5-compatible parts.
3. Wraps them in an FTS5 `NEAR` group or phrase query so all parts must appear adjacently.

**In `_execute_search`**, replace the term-cleaning loop:

```python
# Current (broken):
for term in query.strip().split():
    clean_term = "".join(c for c in term if c.isalnum() or c in ("-", "_"))
    if clean_term:
        raw_terms.append(clean_term)

# Proposed:
for term in query.strip().split():
    # Strip only characters that are not alphanumeric, dot, hyphen, or underscore
    clean_term = "".join(c for c in term if c.isalnum() or c in (".", "-", "_"))
    if not clean_term:
        continue

    if "." in clean_term:
        # FTS5 tokenizes on dots, so split and build a NEAR group
        # e.g. "0.100.0" → NEAR("0" "100" "0", 0)
        parts = [p for p in clean_term.split(".") if p]
        if parts:
            raw_terms.append(("dotted", parts))
    else:
        if len(clean_term) >= 1:  # Allow single-char tokens when from dotted terms
            raw_terms.append(("simple", clean_term))
```

Then update `_fmt_term` and the FTS5 query builder to handle the two term types:

```python
def _fmt_term(t):
    if isinstance(t, tuple):
        kind, val = t
        if kind == "dotted":
            # NEAR/0 means all parts must be adjacent in order
            parts_q = " ".join(f'"{p}"' for p in val)
            return f"NEAR({parts_q}, 0)"
        else:
            return f'"{val}"*' if prefix else f'"{val}"'
    return f'"{t}"*' if prefix else f'"{t}"'
```

### Step 2: Handle the minimum-length filter

The current code drops tokens shorter than 2 characters. For dotted terms like `0.100.0`, the parts `0` are single characters but are meaningful within the phrase. The fix above handles this by keeping the phrase intact — the individual parts don't need to pass a length filter because they are part of a NEAR group.

For standalone single-character queries (not from dotted terms), keep the minimum length filter to avoid noise.

### Step 3: Alternative — simpler approach using FTS5's built-in tokenization

A simpler fix that may be sufficient:

1. **Don't strip dots from the query.** Pass the dotted term to FTS5 directly as a quoted phrase.
2. FTS5 will tokenize it the same way it tokenized the indexed content (splitting on dots).
3. A quoted phrase query `"0 100 0"` in FTS5 matches tokens appearing consecutively.

```python
for term in query.strip().split():
    # Allow dots through — FTS5 handles them as token separators
    clean_term = "".join(c for c in term if c.isalnum() or c in (".", "-", "_"))
    if clean_term:
        raw_terms.append(clean_term)
```

And in `_fmt_term`, let FTS5 handle tokenization of the quoted string naturally:

```python
def _fmt_term(t: str) -> str:
    return f'"{t}"*' if prefix else f'"{t}"'
```

FTS5 will tokenize `"0.100.0"` inside the quotes into a phrase query `"0" "100" "0"`, matching those three tokens in sequence. This is the simplest path.

> [!IMPORTANT]
> **Recommended approach:** Start with Step 3 (the simpler approach). Test it against the benchmark queries: `0.100.0`, `app.mount`, `main.py`. If FTS5's phrase tokenization handles these correctly, skip the NEAR-based approach. Only fall back to Step 1 if FTS5 doesn't handle quoted dotted phrases well.

## Files to change

| File | Change |
| --- | --- |
| [`src/pctx/index.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/index.py#L494-L498) | Update the term-cleaning loop in `_execute_search` to preserve dots |
| [`tests/test_search.py`](file:///c:/Users/nshri/Github/pctx/tests/test_search.py) | Add test cases for dotted queries |

## Tests to add

1. **`test_search_dotted_version`** — Index a doc with `## Release 0.100.0` and body mentioning `0.100.0`. Search for `0.100.0`. Expect at least one result with the correct section address.
2. **`test_search_dotted_identifier`** — Index a doc with `app.mount` in body. Search for `app.mount`. Expect results.
3. **`test_search_dotted_filename`** — Index a doc mentioning `main.py`. Search for `main.py`. Expect results.
4. **`test_search_dotted_no_false_positives`** — Search for `0.999.0` in a corpus that only contains `0.100.0`. Expect zero results (the phrase must match, not just the individual parts).
5. **`test_search_existing_queries_unchanged`** — Run existing search tests to verify no regression.

## Verification

```bash
# After fix, in a test corpus:
pctx search "0.100.0"       # Should return the release notes section
pctx search "app.mount"     # Should return the mount section
pctx search "main.py"       # Should return sections mentioning main.py

# Existing tests must still pass:
pytest tests/test_search.py -v
```

## Risk

- **Low risk.** The change is confined to the query sanitizer. FTS5 indexing is unaffected.
- **Edge case:** Terms like `...` or `.hidden` — the sanitizer should handle these gracefully (strip leading/trailing dots, skip empty results).
