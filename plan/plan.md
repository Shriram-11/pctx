# **PCTX: Implementation Plan**

v1

Local-first

Python + SQLite

## **1. Architecture**

I'd use a relatively small architecture with four core modules.

**CLI Layer**

argparse · commands · argument validation

**Parser**

Markdown → section tree

**Index**

SQLite · hashes · FTS5

**Renderer**

Text · JSON · truncation

**Storage**

.pctx/index.sqlite

Shared data models connect the modules. Keep CLI logic out of the parser and database layer.

Suggested project structure:

```
pctx/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── src/
│   └── pctx/
│       ├── __init__.py
│       ├── cli.py
│       ├── parser.py
│       ├── index.py
│       ├── render.py
│       └── models.py
├── tests/
│   ├── fixtures/
│   │   ├── basic.md
│   │   ├── nested.md
│   │   ├── duplicate-headings.md
│   │   ├── setext.md
│   │   ├── frontmatter.md
│   │   ├── fenced-code.md
│   │   ├── no-headings.md
│   │   └── large-section.md
│   ├── test_parser.py
│   ├── test_index.py
│   ├── test_cli.py
│   ├── test_search.py
│   └── test_render.py
└── .gitignore
```

One addition I'd make to your original structure is `models.py`. It prevents different modules from inventing their own representations of documents and sections.

## **2. Phase-by-phase execution**

**Phase 1: Project scaffolding**

Foundation

Estimated: 1–2 hours

- Initialize project with `uv`.
- Configure Hatchling and `pyproject.toml`.
- Add CLI entry point.
- Implement `pctx --help`.
- Add basic pytest configuration.

**Deliverable:** An installable CLI with five registered subcommands.

**Verification:**

```
uv tool install -e .
pctx --help
pctx index --help
```

**Phase 2: Fixture-driven parser specification**

Estimated: 2–3 hours

- Create fixture Markdown files.
- Cover nested and duplicate headings.
- Test ATX and Setext headings.
- Test fenced code containing `#`.
- Test YAML front matter.
- Test documents without headings.
- Test large sections.

Define expected section trees for every fixture before implementing the parser.

**Deliverable:** A test suite defining expected parser behaviour.

**Verification:**

```
pytest tests/test_parser.py
```

Initially, these tests can fail. That's intentional.

**Phase 3: Markdown parser**

Estimated: 4–6 hours

Implement `parser.py`.

- Parse Markdown using markdown-it-py.
- Extract heading hierarchy.
- Generate stable section addresses.
- Calculate line ranges.
- Extract source slices.
- Estimate token counts.
- Generate document-level L0 summaries.

**Deliverable:** A deterministic Markdown-to-section-tree parser.

**Verification:**

- Exact tree structure.
- Correct line ranges.
- Correct addresses.
- No false headings inside code fences.
- Source slices reproduce the original content.

**Phase 4: SQLite indexing**

Estimated: 4–6 hours

Implement `index.py`.

- Create SQLite schema.
- Store documents and sections.
- Calculate SHA-256 content hashes.
- Detect new and modified files.
- Skip unchanged files.
- Remove deleted files.
- Implement FTS5 indexing.

**Deliverable:** A persistent, incrementally maintained local index.

**Verification:**

- First indexing processes all files.
- Second indexing processes zero unchanged files.
- Editing one document updates only that document.
- Deleting a document removes its records and search entries.
- Failed indexing doesn't leave partially updated document data.

**Phase 5: Retrieval commands**

Estimated: 5–7 hours

Implement `ls`, `outline`, and `show`.

- `ls`: list indexed documents and summaries.
- `outline`: display heading hierarchy and addresses.
- `show`: retrieve section content.
- Implement `--depth`.
- Implement `--max-tokens`.
- Implement compact text and JSON rendering.

**Deliverable:** Agents can navigate documentation without reading entire files.

**Verification:**

- Snapshot tests for text output.
- JSON schema/output tests.
- Byte-exact source extraction.
- Depth expansion and stubs.
- Token-cap enforcement.

**Phase 6: Search**

Estimated: 3–4 hours

Implement FTS5 search.

- Search titles, headings and body text.
- Use BM25 ranking.
- Weight heading matches more heavily.
- Return section addresses.
- Include short snippets.
- Support JSON output.

**Deliverable:** Relevant documentation sections can be found using keywords.

**Verification:**

- Heading match ranks above body-only match for an equivalent query.
- Search returns valid addresses.
- Deleted and modified documents produce correct results.
- Empty and malformed queries are handled gracefully.

**Phase 7: Agent integration and real-world validation**

Release candidate

Estimated: 3–4 hours

- Write README.
- Create `AGENTS.md` usage instructions.
- Run against a real documentation repository.
- Check summaries and token estimates.
- Test the full agent navigation workflow.
- Fix usability issues discovered during testing.

**Deliverable:** A usable v0.1 CLI ready for local experimentation.

**Estimated total: 22–32 hours of implementation work.**

I'd allocate approximately 4–5 working days, leaving some room for unexpected Markdown edge cases.

## **3. Important design decisions**

These are the three decisions I'd settle before implementation because they affect multiple modules.

### **A. Stable section addresses**

My recommendation:

```
architecture.md
├── Overview
│   ├── Goals
│   └── Constraints
├── Design
│   ├── Components
│   └── Components (duplicate)
└── Deployment
```

Addresses:

```
architecture.md#overview
architecture.md#overview/goals
architecture.md#overview/constraints
architecture.md#design
architecture.md#design/components
architecture.md#design/components-2
architecture.md#deployment
```

Rules:

1. Convert heading text to lowercase.
2. Remove Markdown formatting.
3. Replace whitespace with hyphens.
4. Remove punctuation.
5. Resolve duplicate sibling headings with numeric suffixes.
6. Build hierarchical addresses using parent slugs.
7. Keep paths relative to the indexed root.

One important distinction: these are deterministic addresses, not guaranteed permanent IDs. Renaming a heading or inserting an earlier duplicate can change an address. That's acceptable for v1.

### **B. Token estimation**

Don't introduce a tokenizer dependency yet.

Use a deterministic approximation:

```
def estimate_tokens(text: str) -> int:    return max(1, len(text.encode("utf-8")) // 4)
```

This is approximate, not a guarantee of compatibility with any particular LLM tokenizer.

The important property is consistency: indexing and retrieval must use the same estimation method.

### **C.&#x20;**`show --max-tokens`**&#x20;truncation policy**

I'd use a hierarchical approach.

Priority:

1. Include complete child sections where possible.
2. If a section is too large, include complete paragraphs.
3. If a single paragraph exceeds the remaining budget, truncate at a safe text boundary.
4. Always include a truncation marker and continuation address.

Example:

```
# Authentication

Authentication is handled by the central service.

## API Keys

API keys are generated for each integration.

[TRUNCATED]
Continue from: docs/authentication.md#authentication/api-keys
```

The hard cap should apply to the content budget, with a documented policy for metadata and truncation markers.

Don't silently omit content. The agent must know that more content exists.

## **4. SQLite schema proposal**

I'd start with three logical tables and an FTS5 virtual table.

| Table          | Purpose                                      |
| -------------- | -------------------------------------------- |
| `documents`    | File metadata, hash, summary                 |
| `sections`     | Heading hierarchy, addresses, ranges, tokens |
| `sections_fts` | Full-text search                             |

Possible section representation:

```
CREATE TABLE sections (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL,
    parent_id INTEGER,
    address TEXT NOT NULL UNIQUE,
    heading TEXT,
    slug TEXT,
    level INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY(doc_id) REFERENCES documents(id)
);
```

For FTS5, I'd index heading and body separately so ranking can be controlled:

```
CREATE VIRTUAL TABLE sections_fts USING fts5(
    address UNINDEXED,
    heading,
    content
);
```

Then use BM25 column weights to prioritize heading matches.

A practical detail: enable SQLite foreign keys on every connection and use transactions for per-file updates.

## **5. CLI contract**

I'd freeze the interface early so the implementation doesn't drift.

| Command                         | Responsibility             |
| ------------------------------- | -------------------------- |
| `pctx index ./docs`             | Build/update index         |
| `pctx ls`                       | List documents             |
| `pctx outline path/doc.md`      | Display document hierarchy |
| `pctx show path/doc.md#section` | Retrieve content           |
| `pctx search "authentication"`  | Search indexed content     |

Common options:

```
--json
```

Show-specific:

```
--depth 2
--max-tokens 2000
```

A few additional considerations:

- `index` should accept an explicit root directory.
- Other commands should resolve the index from the current directory or an explicitly supplied index location.
- Missing index should produce an actionable error.
- JSON output should be machine-readable, with no progress messages mixed into stdout.
- Diagnostics should go to stderr.

## **6. Agent workflow**

This is arguably the most important part of the entire project.

An agent shouldn't need to understand how SQLite, Markdown parsing or indexing works.

It should have a simple workflow:

1\. Discover

**Find available documents**

```
pctx ls --json
```

2\. Navigate

**Inspect document structure**

```
pctx outline architecture.md --json
```

3\. Retrieve

**Read only relevant sections**

```
pctx show architecture.md#design \
  --depth 2 \
  --max-tokens 3000
```

4\. Continue

**Follow continuation addresses if truncated**

```
pctx show architecture.md#design/components
```

The `AGENTS.md` snippet should explicitly instruct agents to:

- Prefer `pctx` over reading entire documentation files.
- Start with `ls` when discovering documentation.
- Use `outline` before retrieving unfamiliar documents.
- Retrieve only relevant sections with `show`.
- Follow continuation addresses when content is truncated.
- Use `search` when they don't know which document contains the answer.

## **7. Definition of Done**

Before calling v1 complete, I'd use this checklist.

**Release checklist**

# **0/16**

CLI installs through uv and all five commands work

Nested Markdown documents are indexed correctly

Setext headings and fenced code are handled correctly

Duplicate headings produce distinct addresses

Line ranges and source extraction are correct

L0 summaries follow the specified fallback order

Incremental indexing skips unchanged files

Modified files are updated transactionally

Deleted files are removed from SQLite and FTS5

Depth-limited output produces child stubs

Max-token output respects its content budget

JSON output is consistent and machine-readable

BM25 search prioritizes heading matches

pytest covers all major edge cases

AGENTS.md demonstrates the navigation workflow

Real-world documentation repository successfully indexed

## **8. What I'd deliberately NOT build**

Keep these outside v1:

- MCP server.
- File watchers.
- Embeddings.
- LLM-generated summaries.
- Cross-document reference graphs.
- Multiple document formats.
- PyPI publishing.

There's a temptation to make this an elaborate agent knowledge-management system. Resist it.

First prove that deterministic indexing, hierarchical retrieval and token-aware context delivery solve the problem.

## **My recommendation on implementation order**

I'd make one small adjustment to your original sequence:

**Build the parser and its tests before touching SQLite.**

The parser is the foundation. If addresses, hierarchy or source ranges are wrong, every downstream feature inherits those problems.

I'd also make one additional test mandatory: retrieve a section and reconstruct its exact original source. This will catch subtle bugs involving line boundaries, nested sections and Markdown formatting.

The most interesting eventual benchmark will be:

- How many tokens does an agent consume when navigating documentation conventionally?
- How many tokens does it consume using PCTX?
- Does it still retrieve the information necessary to complete the same task?

That gives you an actual measure of whether the tool is useful, rather than just whether the CLI works.

**I'd target a working v1 in five days, not a polished product in two weeks.** Get it running against your Governance documentation, observe how an agent uses it, and let that experiment decide what v2 should become.
