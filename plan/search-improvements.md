# Search Improvements Plan

## Current state

`pctx search` works through SQLite FTS5 with BM25 ranking. It is fast and reliable but has two hard limitations:

1. **Exact-term only.** FTS5 requires query terms to match exactly what is in the index. A search for `"autentication"` returns nothing even though `"authentication"` is indexed.
2. **No similarity.** There is no way to ask "what documents are most like this one?" or "what other sections talk about the same topic as this address?" Without that, agents navigating an unfamiliar corpus have to guess keywords.

Everything below is strictly about search and document similarity. It does not touch indexing of source code, MCP, or other roadmap areas.

---

## Goal

After these improvements an agent (or user) should be able to:

- Find the right section even with a typo or partial term.
- Discover related sections without knowing the exact keyword.
- Navigate by example: "show me more sections like this one."
- See *why* a result matched, not just that it did.

---

## Phase S1 — Fuzzy term matching

**Problem:** `pctx search "autentication"` returns nothing.  
**Fix:** Before hitting FTS5, generate fuzzy candidates and fall back when the exact search is empty.

### How it works

```
query term → edit-distance candidates → FTS5 OR query → ranked results
```

1. Split the query into individual terms.
2. For each term that returns no FTS5 hits:
   - Walk the FTS5 vocabulary (via `fts5vocab`) and collect all terms within edit distance 1 or 2 (using the standard Wagner–Fischer DP algorithm — no external dependency needed).
   - Filter candidates to those whose edit distance / term length ratio is below a configurable threshold (default: 2 edits for terms ≥ 6 chars, 1 edit for shorter terms).
3. Build a secondary FTS5 `OR` query from the candidates and re-run.
4. Merge and re-rank the combined results with the exact hits scoring higher than fuzzy hits.
5. Report the correction in output: `(fuzzy match: "autentication" → "authentication")`.

### New CLI flag

```bash
pctx search "autentication" --fuzzy          # enable fuzzy fallback (off by default)
pctx search "autentication" --fuzzy --json   # fuzzy flag in JSON: "matched_as": "authentication"
```

Fuzzy is opt-in so the default behaviour stays deterministic and fast.

### JSON output additions

```json
{
  "address": "docs/guide.md#authentication",
  "heading": "Authentication",
  "snippet": "...",
  "score": -1.42,
  "match_kind": "fuzzy",
  "matched_term": "authentication"
}
```

### Implementation notes

- `fts5vocab` virtual table is built into SQLite — no extra dependency.
- Edit-distance function in pure Python (~25 lines); no C extension needed.
- The vocabulary walk is bounded: skip any candidate term whose first character differs from the query term's first character (optional heuristic to keep it fast on large corpora).

### Tests

- Exact search still returns exact results unchanged.
- Single-character typo is corrected in heading-only matches.
- Two-character typo is corrected for long terms (≥ 8 chars).
- Completely wrong query returns empty even with `--fuzzy`.
- `match_kind` field is `"exact"` for normal hits and `"fuzzy"` for corrected hits.

---

## Phase S2 — Prefix / partial-term search

**Problem:** `pctx search "auth"` does not match `"authentication"`.  
**Fix:** Add `--prefix` mode that appends `*` to each term in the FTS5 query.

FTS5 supports prefix queries natively: `"auth"*` matches any term beginning with `auth`. This is essentially free — one-line change to query construction.

```bash
pctx search "auth" --prefix
```

Output is identical to current search. `match_kind` becomes `"prefix"` in JSON.

This is a separate flag from `--fuzzy` and can be combined: `--fuzzy --prefix`.

---

## Phase S3 — Similar section / similar document search

**Problem:** No way to ask "what else talks about the same topic as `docs/api.md#rate-limiting`?"  
**Fix:** A new `similar` command that uses TF-IDF term weighting to find sections with the most content overlap.

### New command

```bash
pctx similar <address>              # most similar sections to a given section
pctx similar <address> --top 5     # limit results (default: 5)
pctx similar <address> --json
```

```bash
pctx similar docs/api.md#rate-limiting
```

Output:

```
docs/api.md#quotas                   Quotas              score: 0.84
docs/api.md#throttling               Throttling          score: 0.71
docs/guide.md#limits                 Limits              score: 0.58
```

### How it works (pure SQLite, no embeddings)

1. Retrieve the content of the target section.
2. Extract the top-N most significant terms using TF-IDF computed from FTS5's internal statistics:
   - **TF** (term frequency): count of term occurrences in the target section.
   - **IDF** (inverse document frequency): derived from `matchinfo()` or `fts5vocab` for each term.
3. Build a weighted FTS5 `OR` query using those top terms.
4. Run the query, exclude the source section from results.
5. Score results by overlap of their own top terms with the source section's terms.

No embeddings, no model calls, no network. Everything runs on the existing SQLite index.

### Why no embeddings (yet)

Semantic embeddings would give higher-quality similarity but require:
- A model call or local model (~100 MB+).
- Storing dense vectors (increases DB size substantially).
- Keeping vectors in sync with text updates.

TF-IDF over FTS5 gives 70–80% of the recall for 0% of the dependency cost. This is explicitly in line with the design principle: **prefer syntax-aware data and FTS before considering embeddings**.

Embeddings can be layered on later as a `--semantic` flag without changing the command shape.

### JSON output

```json
[
  {
    "address": "docs/api.md#quotas",
    "heading": "Quotas",
    "score": 0.84,
    "shared_terms": ["rate", "limit", "request", "exceeded"],
    "estimated_tokens": 320
  }
]
```

### Tests

- Returns `--top N` results, never the source address itself.
- Score is 1.0 for a section identical in content.
- Score is 0 for a section with zero shared significant terms.
- Handles L0 document addresses (not just fragment addresses).
- `--json` output validates against the schema above.

---

## Phase S4 — Search result quality and output improvements

Smaller, high-value refinements to existing search output.

### S4-a: Snippet quality

The current `snippet()` call uses a fixed window of 20 tokens and HTML bold markers (`<b>`, `</b>`). In a terminal these render as literal tags.

- Switch to plain-text highlight markers (e.g. `**term**` or `>>>term<<<`) in text mode; keep HTML markers only in JSON where callers can handle them.
- Increase snippet window to 30 tokens for more context.
- Include the section heading in text output even when the match is in body content, so the agent knows which section it landed in.

### S4-b: Result deduplication

If a query matches both a parent section and a child section, both are currently returned. The parent result is often redundant.

- Detect when a child result is already included and the parent's snippet covers the same match.
- Suppress the parent if the child result has a higher score and is within the same line range.
- Configurable via `--no-dedup` flag to restore old behaviour.

### S4-c: Pagination

Large corpora can produce many results. Add `--limit` (default: 20, already exists) and `--offset` for page-based retrieval.

```bash
pctx search "authentication" --limit 10 --offset 10   # second page
```

JSON includes `"total_hits"` (capped at a reasonable ceiling, e.g. 100) and `"offset"` so agents know if more results exist.

### S4-d: Search within a document

Scope search to a single document or subtree.

```bash
pctx search "rate limiting" --in docs/api.md
pctx search "rate limiting" --in docs/   # all documents under docs/
```

Implemented as a SQL `AND d.path LIKE ?` filter on the FTS join. No schema change needed.

---

## Implementation order

| Step | Phase | Effort |
|------|-------|--------|
| 1 | S4-a: snippet quality | ~1 hour |
| 2 | S4-d: search within document | ~1 hour |
| 3 | S2: prefix search (`--prefix`) | ~30 minutes |
| 4 | S4-b: deduplication | ~2 hours |
| 5 | S4-c: pagination | ~1 hour |
| 6 | S1: fuzzy matching | ~4–5 hours |
| 7 | S3: similar command | ~6–8 hours |

Start with the cheap, high-impact wins (S4-a, S4-d, S2). Fuzzy and similar are more involved but are the headline features.

---

## What is deliberately out of scope

- **Semantic / embedding-based search.** Deferred. TF-IDF similar is good enough for v1 of this feature set.
- **Multi-language stemming / stopword lists.** FTS5's built-in tokenizer handles basic stemming. Custom stemming adds complexity without enough payoff for a docs tool.
- **Query syntax (AND, OR, NOT via CLI).** FTS5 already supports this internally. Exposing it in the CLI risks fragile query escaping. Deferred until there is a clear user need.
- **Search history or saved queries.** Out of scope for a local CLI tool.
