# Bug Fix: Parent Section Ranks Below Child, Then Truncates Before Answer

## Problem

When searching for "CORS" in the FastAPI corpus, the **preflight subsection** (179 tokens, no `allow_origins` info) ranked #1, while the **main CORS section** (which contains the actual `allow_origins` configuration) ranked #2. Worse, when the agent fetched the main section with `--max-tokens 800`, it truncated before reaching the `allow_origins` content.

This is a two-part problem:

1. **Ranking:** A narrow child section with the query term in its heading outranks the broader parent section that actually contains the answer.
2. **Truncation:** Even when the right section is fetched, the section's own body is not prioritized over its children's content, so truncation cuts off the answer.

### Root cause

**Ranking issue:** BM25 naturally favors shorter documents where the query term is proportionally more prominent. The preflight subsection is 179 tokens with "CORS" in the heading, so its BM25 score is very high. The main CORS section is much larger (includes all child content), diluting the term frequency.

**Truncation issue:** [`render.py` `render_show_text`](file:///c:/Users/nshri/Github/pctx/src/pctx/render.py#L165-L233) renders a section's content as its full source text — which includes all child sections inline. When `--max-tokens` truncates, it cuts from the end, which may clip the section's own body if it appears after child content, or clip later children that contain the answer. The section's **own introductory body** (the text between the section heading and the first child heading) is not separated from child content.

**Dedup interaction:** [`_dedup_search_rows`](file:///c:/Users/nshri/Github/pctx/src/pctx/index.py#L154-L180) suppresses parents when a child has an **equal or better** score. In the CORS case, the child (preflight) has a better BM25 score than the parent, so dedup suppresses the parent entirely. The agent never sees the main CORS section in results.

## Fix

This requires changes in three areas: search ranking, dedup logic, and content rendering.

### Part A: Improve parent–child ranking in search results

#### A1: Separate own-body content from child content in the index

The core issue is that each section's `content` column stores the **full subtree** (the section's own text plus all descendant text). This means:

- Parent sections are always larger, diluting BM25 scores.
- The same text is indexed multiple times (once in the parent, once in each child).

> [!NOTE]
> This is also listed as Phase 0 item 5 in the roadmap: "Store each section's own body only."

**Proposed change:** Store only the section's **own body** in the `content` column — the text between the section's heading and the first child heading (or end of section if no children).

**In `parser.py` `_build_sections`**, after computing spans, calculate the own-body range:

```python
# For each heading, own_body runs from the heading line to the start of
# the first direct child heading (or end of section if no children).
# 
# Step 1: Identify direct children for each heading
# Step 2: own_end = min(first_child.start_line, section.end_line)
# Step 3: Store own-body content only
```

**Implementation sketch:**

```python
for i, h in enumerate(headings):
    start, end = spans[i]
    
    # Find first child: next heading with level == h.level + 1
    own_end = end
    for j in range(i + 1, len(headings)):
        if headings[j].level <= h.level:
            break  # No more children
        if headings[j].level == h.level + 1:
            own_end = headings[j].line + fm_offset - 1
            break
    
    # own-body content
    own_content = ''.join(source_lines[start:own_end + 1])
    
    # full content (for show command, which needs the full subtree)
    full_content = ''.join(source_lines[start:end + 1])
```

This requires a schema change — either:

**Option 1:** Replace `content` with own-body content only. The `show` command reconstructs full content from child sections on the fly.

**Option 2:** Add a second column `own_content` for search indexing, keep `content` for the `show` command.

> [!IMPORTANT]
> **Recommended: Option 2** for the initial fix. It's backward-compatible — the `show` command continues working unchanged. The FTS5 index is rebuilt to use `own_content` instead of `content`.

Schema change:

```sql
ALTER TABLE sections ADD COLUMN own_content TEXT NOT NULL DEFAULT '';
```

FTS5 trigger update:

```sql
-- Index own_content instead of content for search
INSERT INTO sections_fts(rowid, address, heading, content)
VALUES (new.id, new.address, coalesce(new.heading, ''), new.own_content);
```

#### A2: Boost heading-level matches with a level-aware weight

Add a small BM25 boost for sections at the level where the term appears in the heading. When a query term matches a heading, prefer the section whose heading-level scope is most relevant.

This is a lighter-touch fix if A1 is too invasive for a first pass:

```python
# After getting BM25 results, apply a level-based adjustment
# Parent sections (lower level) get a small boost when the query matches their heading
# This counteracts BM25's length bias toward shorter child sections
```

However, this is fragile and query-dependent. **A1 is the proper fix.**

### Part B: Fix dedup to preserve parent when child doesn't contain the answer

The current dedup in [`_dedup_search_rows`](file:///c:/Users/nshri/Github/pctx/src/pctx/index.py#L154-L180) suppresses parents when a child has an equal or better score. But after fix A1 (indexing own-body only), parent and child are **independent documents** with non-overlapping content. The dedup logic should change:

```python
def _dedup_search_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    """After A1: dedup is simpler because content doesn't overlap.
    
    Only suppress an L0 document root if a child section from the same
    document also matched (the root's own-body is usually just front matter).
    """
```

If A1 is **not** implemented (own-body indexing deferred), adjust the dedup threshold:

```python
# Current: suppress parent if child score <= parent score
# Proposed: suppress parent only if child score is SIGNIFICANTLY better
# (e.g., child score < parent score * 0.8) AND child contains the query in heading
if same_span_root or (other["score"] < row["score"] * 0.8 and other["level"] > row["level"]):
    suppressed = True
```

This is a stopgap — the proper fix is A1.

### Part C: Prioritize section's own body in `show` truncation

When `--max-tokens` is set, the `show` command should render the section's **own body first**, then child section stubs, rather than rendering the full subtree and truncating from the end.

**In [`render.py` `render_show_text`](file:///c:/Users/nshri/Github/pctx/src/pctx/render.py#L165-L233):**

Currently, `content_to_render` is the section's full source text (heading + own body + all children). When `--depth` is set, it trims at the cutoff line. But even with `--depth 1`, the content includes the full text up to the first child at depth > 1, which may be a lot.

The fix:

```python
# When depth is set, extract the section's own-body lines first
# (from section heading to first direct child heading).
# Then append child heading stubs.
# This ensures the section's own content is never truncated
# in favor of a child's content.

if depth is not None:
    base_level = section.level
    
    # Find the first direct child heading
    first_child_line = None
    for child in children:
        rel_depth = child.level - base_level if base_level > 0 else child.level
        if rel_depth == 1:
            first_child_line = child.start_line
            break
    
    if first_child_line is not None:
        # Own body: from section start to first child
        rel_cut = first_child_line - section.start_line
        content_lines = section.content.splitlines(keepends=True)
        own_body = "".join(content_lines[:rel_cut]).rstrip()
        
        # Then include child content up to depth limit
        # (existing logic for depth-limited content follows)
```

This ensures that when the token budget is tight, the section's own introductory text (which often contains the most important information) is included before any child content.

## Files to change

| File | Change | Priority |
| --- | --- | --- |
| [`src/pctx/parser.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/parser.py) | Compute own-body content for each section | High (Part A1) |
| [`src/pctx/models.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/models.py) | Add `own_content` field to `Section` dataclass | High (Part A1) |
| [`src/pctx/index.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/index.py) | Schema migration for `own_content`; update FTS triggers; update dedup | High (Parts A1, B) |
| [`src/pctx/render.py`](file:///c:/Users/nshri/Github/pctx/src/pctx/render.py) | Prioritize own-body in `show` truncation | Medium (Part C) |
| [`tests/test_search.py`](file:///c:/Users/nshri/Github/pctx/tests/test_search.py) | Test parent–child ranking | High |
| [`tests/test_render.py`](file:///c:/Users/nshri/Github/pctx/tests/test_render.py) | Test own-body-first truncation | Medium |

## Implementation order

1. **Part A1** (own-body content) — This is the foundational fix. Everything else builds on it.
2. **Part C** (show truncation) — Quick follow-up once own-body is available.
3. **Part B** (dedup adjustment) — May not be needed after A1, evaluate after testing.

## Tests to add

### Fixture for ranking tests

```markdown
# CORS (Cross-Origin Resource Sharing)

Configure CORS in your application using `allow_origins`, `allow_methods`,
and `allow_headers` parameters.

## Preflight Requests

Browsers send preflight OPTIONS requests before the actual request.

## Configuration Example

```python
app.add_middleware(CORSMiddleware, allow_origins=["*"])
```⁠
```

### Test cases

1. **`test_parent_ranks_above_narrow_child`** — Search for "CORS". The main CORS section (which contains `allow_origins` in its own body) should rank at or above the "Preflight Requests" subsection.
2. **`test_own_body_indexed_separately`** — After indexing, the CORS main section's FTS content should contain `allow_origins` but not the full text of the Preflight subsection.
3. **`test_dedup_keeps_parent_with_unique_content`** — When parent's own-body has unique matching content, dedup should not suppress it.
4. **`test_show_own_body_first_in_truncation`** — `show cors-doc.md#cors --depth 1 --max-tokens 100`. The output should include the own-body text (`allow_origins`) before any child stubs, even with a very tight token budget.
5. **`test_show_full_content_without_depth`** — Without `--depth`, `show` still renders the full subtree (backward compatible).
6. **`test_index_size_reduction`** — After switching to own-body indexing, the FTS index should be significantly smaller (the 15 MB → ~3–5 MB for the FastAPI corpus).

## Verification

```bash
# After fix:
pytest tests/test_search.py tests/test_render.py -v

# Manual check on the CORS case:
pctx search "CORS"               # Main section should be in top results
pctx show docs.md#cors --depth 1 --max-tokens 200   # Own body first

# Index size check:
pctx index ./docs
ls -la .pctx/index.sqlite        # Should be significantly smaller
```

## Risk

- **High risk / high reward.** Part A1 (own-body indexing) is a schema change that affects every section in the index. It requires a full re-index and touches multiple modules.
- **Mitigated by:** The parser version bump (from bug-02) already forces re-indexing. These changes can be bundled into the same version bump.
- **Backward compatibility:** The `show` command continues to render full subtree content. Only the FTS index changes what it searches over.
- **Phased rollout:** If A1 is too risky, implement Part C (truncation fix) first — it's self-contained and addresses the immediate user-facing symptom (truncation before the answer).
