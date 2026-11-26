# PCTX Roadmap

Order the roadmap by measurement, not by features: on a 159-file FastAPI docs corpus, `pctx` v0.1 roughly matches a grep plus ranged-read baseline on small docs, and it failed the one big-file lookup.

- **Code health is good.** All 98 tests pass. Indexing 159 files takes 1.3s cold and 0.1s incrementally.
- **Token cost is about even with grep.** On five small-doc lookups, `pctx` text output used 8,173 tokens against 11,171 for grep plus an 80-line window. `pctx` JSON used 10,855.
- **Two verified bugs hurt the exact cases `pctx` should win.** Queries containing dots return nothing, and the top CORS hit did not contain the answer.
- **The plan:** harden v0.1, build a benchmark harness that gates publishing, then add the MCP server and agent ergonomics. Defer or cut the rest.

## Benchmark findings: `pctx` vs `grep`

`pctx` beat a realistic grep baseline by about 27% on five small-doc lookups (text output), tied with it on JSON output, and returned nothing for the big-file task.

Tokens per lookup, discovery included, estimated as UTF-8 bytes divided by 4. The grep window is `grep -rn | head -40` plus an 80-line read from the first match in the right file.

| Task | `grep` + whole file | `grep` + 80-line window | `pctx` JSON | `pctx` text | Answer in `pctx` output? |
| --- | ---: | ---: | ---: | ---: | --- |
| enable CORS | 3,164 | 3,022 | 1,929 | 1,357 | No |
| background task | 3,231 | 2,807 | 2,986 | 2,431 | Yes (rank 4) |
| exclude unset | 4,751 | 1,419 | 1,861 | 1,398 | Yes |
| static files | 1,054 | 1,046 | 1,933 | 1,409 | Yes |
| add middleware | 5,958 | 2,877 | 2,146 | 1,578 | Yes |
| release `0.100.0` (185K-token file) | 185,577 | 1,187 | 2 | 5 | No (0 results) |
| **Total, first five** | **18,158** | **11,171** | **10,855** | **8,173** | |

The grep window contained the answer in all six cases. `pctx` JSON cost more than grep on two of the five small tasks (background task, static files).

### What the numbers show

- Text output is about 25% cheaper than JSON (8,173 vs 10,855 tokens). Agents should default to text.
- `search` has no `--limit`, so an agent gets 20 hits, which costs 1.2–2.1K tokens in JSON (0.9–1.6K in text) before any `show` call.
- `pctx ls --json` on all 159 docs costs 5,585 tokens, and it is step 1 of the `AGENTS.md` workflow.

### Verified bugs

- **Dots in queries return nothing.** `0.100.0`, `app.mount` and `main.py` each return 0 results, because the sanitizer strips every character except letters, digits, `-` and `_`. The query `0 100 0` works and ranks the right section 2nd. Passing the term as a quoted phrase should fix this, since FTS5 already splits on punctuation; I have not tested that change.
- **The top CORS hit lacked the answer.** Rank 1 was the preflight subsection (179 tokens, no `allow_origins`). The main section was rank 2 and hit the 800-token budget (`truncated: true`) before reaching `allow_origins`. Changing `--depth` did not help.
- **Heading ids leak into addresses.** About half the headings in this corpus (1,146 of about 2,271) use the `{ #custom-id }` syntax, and the whole attribute block is slugified into the address, for example `cors-cross-origin-resource-sharing-cors-cross-origin-resource-sharing`. Median address length is 62 characters, maximum 399.
- **The index is large.** 15 MB for 1.5 MB of Markdown, because each section stores its full subtree.

> **Correction to the earlier figure.** An earlier run reported a 1.6x saving over whole-file reads. It counted only the top 5 search hits, which an agent cannot request. Use the table above instead.

## Phase 0: Harden v0.1

Fix the verified defects before adding any feature, because every later benchmark inherits them.

1. **Slugs from explicit ids.** Use the `{ #id }` value as the slug. `mdit-py-plugins` is already a dependency, but `parser.py` imports only `markdown_it`. Add a parser version to the content hash, otherwise unchanged files keep their old addresses after the fix.
2. **Search that handles real queries.** Stop stripping dots, so `0.100.0` and `main.py` work. Drop stopwords, add prefix matching or a porter tokenizer, and fall back to `OR` when `AND` finds nothing (`"how do I run tests"` currently returns unrelated pages).
3. **`--limit` on `search`, with a low default.** Search output was the largest cost in the benchmark. Add `--limit` and `--offset`.
4. **Rank parent sections sensibly.** The CORS main section ranked below a subsection, and then truncated before the answer. Investigate preferring the parent on equal matches, and showing a section's own body before its child stubs.
5. **Store each section's own body only.** Rebuild subtrees from line ranges. This should shrink the 15 MB index and remove duplicate parent and child hits. I have not prototyped it.
6. **Make `ls` cheap.** Add `--limit`, `--prefix` and a compact mode. At 159 docs it costs 5,585 tokens.

## Phase 1: Benchmark harness (gate)

Publish only if `pctx` clearly beats grep plus ranged reads at equal task success. The first benchmark measured retrieval cost only, and it never ran an agent.

- **Baseline:** grep plus ranged reads, which is what agents do today. Not whole-file reads.
- **Corpora:** one repo with a few very large docs (FastAPI's `release-notes.md` is 185K tokens, 48% of its corpus) and one with many small docs (FastAPI's other 158 files have a median of about 950 tokens).
- **Tasks:** a fixed set with a gold string each, including big-file lookups like "what changed in 0.100.0" and queries with dots or identifiers.
- **Metrics:** tokens used, task success, and number of tool calls. The first benchmark has no data on the last two.
- **Gate:** Re-run after Phase 0 and compare against the table in the findings section.

## Phase 2: MCP server

Ship the MCP server after the gate, with 3–4 tools at most.

- The CLI already works through a shell, so MCP's gain is discoverability and no per-call process spawn. I have not measured either.
- Tool schemas cost tokens on every session. Keep them small, or they eat the savings the tool exists to create.
- Keep the CLI fully functional. The server wraps the same library code.

## Phase 3: Freshness without watch mode

Check freshness lazily on every query instead of building a watcher.

- A no-change re-index of 159 files took 0.1s, so a hash or mtime check on each query is cheap.
- That makes watch mode and most of `pctx status` unnecessary.
- Keep a cheap `pctx info` (document count, total tokens, last indexed time, index size).

## Phase 4: Agent ergonomics

Attack per-call overhead, since search output and JSON wrapping were the main costs in the benchmark.

1. **`pctx context <addr...>`:** several sections in one token-budgeted call, with overlapping ranges deduplicated. It should come before most other features.
2. **Compact text as the default for agents, JSON opt-in.** Text was about 25% cheaper in the benchmark. Update the `AGENTS.md` examples, which currently use `--json`.
3. **`schema_version` in JSON output**, so the interface is actually stable.
4. **Optional `tiktoken` estimator.** `bytes/4` is crude for code-heavy and non-English docs, and it affects benchmark numbers. This is my judgment; I have not measured the error.

## Defer or cut

Every item from the current post-v1 roadmap that I would not build yet, and why.

| Item | Current roadmap phase | Call | Why |
| --- | --- | --- | --- |
| Multi-format (`.rst`, `.txt`, `.adoc`) | 1 | Defer | FastAPI's docs are all Markdown. Revisit when a real corpus needs it. |
| Trigram or fuzzy search | 3 | Keep, secondary | Helps identifiers like `response_model`. Fix query semantics first, since that was the bigger problem. |
| Cross-document link graph | 3 | Defer | Low value unless the benchmark shows agents failing at discovery. |
| Front-matter tags | 3 | Defer | Same reason as the link graph. |
| Watch mode and `pctx status` | 4 | Cut | A lazy freshness check on each query covers it (Phase 3 above). |
| Diff-aware `show --since` | 5 | Defer | Git already does this. |
| HTML and PDF export | 5 | Cut | Off-mission for an agent navigation tool. |

## Method and caveats

Treat these numbers as a first signal, not proof: six tasks on one corpus, no agent in the loop.

- **Code tested:** `pctx` v0.1.0 at commit `3a27396`, on Python 3.13.18 and SQLite 3.53.1 (FTS5 available). 98 of 98 tests pass when run with an absolute `PYTHONPATH`.
- **Corpus:** FastAPI's `docs/en/docs`, 159 Markdown files, about 384K tokens (`bytes/4`), fetched with a shallow sparse clone in November 2026.
- **Token counting:** `pctx`'s own estimate (UTF-8 bytes divided by 4), not a real tokenizer.
- **Biases in `pctx`'s favor:** I chose the first search hit inside the correct file, and `pctx`'s `show` used `--depth 1 --max-tokens 800` from the `AGENTS.md` example.
- **Biases in grep's favor:** the grep baseline assumes the agent picks the right file and reads the right 80 lines, and it ignores follow-up calls.
- **Not measured:** task success with a real agent, tool-call counts, latency beyond indexing, and any corpus other than FastAPI.
