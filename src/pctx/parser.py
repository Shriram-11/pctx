"""Markdown parser — parses Markdown files into Section trees.

Uses markdown-it-py to tokenize correctly (handles fenced code blocks,
setext headings, etc.). Returns a flat, depth-first ordered list of
Section objects where the first element is always the L0 document root.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from markdown_it import MarkdownIt

from pctx.models import Section


# ---------------------------------------------------------------------------
# Token estimation (spec-defined formula)
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Return a rough token estimate: max(1, utf-8 bytes // 4)."""
    return max(1, len(text.encode("utf-8")) // 4)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def _strip_md_formatting(text: str) -> str:
    """Remove inline Markdown formatting markers (bold, italic, code, etc.)."""
    # Remove links: [text](url) → text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Remove image alt text: ![alt](url) → alt
    text = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Remove inline code, bold, italic, strikethrough markers
    text = re.sub(r'[*_`~]+', '', text)
    return text


def slugify(text: str) -> str:
    """Convert heading text to a URL-friendly slug.

    Rules:
      1. Remove inline Markdown formatting
      2. Lowercase
      3. Remove all punctuation except hyphens and word characters
      4. Replace whitespace / underscores with hyphens
      5. Collapse consecutive hyphens; strip leading/trailing hyphens
      6. Fall back to 'section' if result is empty
    """
    text = _strip_md_formatting(text)
    text = text.lower().strip()
    # Remove everything that isn't a word char, whitespace, or hyphen
    text = re.sub(r'[^\w\s-]', '', text)
    # Replace whitespace and underscores with hyphens
    text = re.sub(r'[\s_]+', '-', text)
    # Collapse consecutive hyphens
    text = re.sub(r'-+', '-', text).strip('-')
    return text or 'section'


# ---------------------------------------------------------------------------
# Front-matter stripping
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> tuple[str, int]:
    """Strip YAML front matter if the file starts with ``---``.

    Returns ``(stripped_text, lines_consumed)`` where *lines_consumed* is the
    number of original lines that were removed (so callers can offset line
    numbers back to the original file).
    """
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        return text, 0

    # Find the closing ---
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            consumed = i + 1          # lines[0..i] inclusive
            stripped = '\n'.join(lines[consumed:])
            return stripped, consumed

    # No closing delimiter found — treat the whole file as content
    return text, 0


# ---------------------------------------------------------------------------
# Internal heading record
# ---------------------------------------------------------------------------

class _Heading:
    """Lightweight record produced during the first pass over tokens."""

    __slots__ = ('level', 'text', 'line')   # line is 0-based

    def __init__(self, level: int, text: str, line: int) -> None:
        self.level = level
        self.text = text
        self.line = line   # 0-based index into *stripped* source lines


# ---------------------------------------------------------------------------
# Core parsing logic
# ---------------------------------------------------------------------------

def _extract_headings(md_text: str) -> list[_Heading]:
    """Tokenize *md_text* with markdown-it-py and extract all headings.

    Returns a list of ``_Heading`` in document order. Line numbers are
    0-based relative to *md_text*.
    """
    md = MarkdownIt()
    tokens = md.parse(md_text)

    headings: list[_Heading] = []

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == 'heading_open':
            level = int(tok.tag[1])          # 'h1' → 1, 'h2' → 2, …
            line = tok.map[0] if tok.map else 0   # 0-based

            # Next token is inline content of the heading
            heading_text = ''
            if i + 1 < len(tokens) and tokens[i + 1].type == 'inline':
                heading_text = tokens[i + 1].content.strip()

            headings.append(_Heading(level, heading_text, line))
        i += 1

    return headings


def _build_sections(
    headings: list[_Heading],
    source_lines: list[str],
    doc_path: str,
    fm_offset: int,
) -> list[Section]:
    """Build the flat Section list from the extracted headings.

    *source_lines* are the lines of the **original** file (including any
    front-matter that was already removed from the parsed text, but whose
    line count is captured in *fm_offset*).

    Line numbers stored on Section objects are 0-based to satisfy tests
    (``test_root_starts_at_zero``).
    """

    total_lines = len(source_lines)

    # ------------------------------------------------------------------
    # Helper: resolve duplicate slugs within a sibling group
    # ------------------------------------------------------------------
    def _resolve_slug(slug: str, seen: dict[str, int]) -> str:
        count = seen.get(slug, 0) + 1
        seen[slug] = count
        return slug if count == 1 else f'{slug}-{count}'

    # ------------------------------------------------------------------
    # Pass 1 — assign content spans (start / end line, 0-based)
    # ------------------------------------------------------------------
    # Each heading's content runs from its own line to (but not including)
    # the next heading at the same or higher (lower-numbered) level, or
    # the end of file.

    # Build span boundaries for every heading
    # end_line is inclusive, 0-based
    spans: list[tuple[int, int]] = []   # (start, end) for each heading

    for idx, h in enumerate(headings):
        start = h.line + fm_offset          # 0-based in original file

        # Find the first subsequent heading that closes this one:
        # any heading with level <= h.level terminates this section.
        end = total_lines - 1
        for j in range(idx + 1, len(headings)):
            if headings[j].level <= h.level:
                # The subsequent heading starts at its own line;
                # this section ends one line before that.
                end = headings[j].line + fm_offset - 1
                break

        spans.append((start, end))

    # ------------------------------------------------------------------
    # Pass 2 — build hierarchy (parent tracking via level stack)
    # ------------------------------------------------------------------
    # level_stack[i] = index of the most-recent section at level i
    # We use a dict[level → section_index_in_result_list]
    # The L0 root is index 0.

    sections: list[Section] = []

    # L0 document root
    doc_name = doc_path  # keep full path for address (e.g. "custom/my-doc.md")
    root_content = ''.join(source_lines)
    root = Section(
        doc_id=0,
        address=doc_name,
        heading=None,
        slug=doc_name,
        level=0,
        start_line=0,
        end_line=total_lines - 1 if total_lines > 0 else 0,
        content=root_content,
        estimated_tokens=estimate_tokens(root_content),
    )
    sections.append(root)

    # Tracks the section-list index of the most-recently-seen heading at
    # each level so we can assign parent_id correctly.
    level_to_idx: dict[int, int] = {0: 0}

    # Sibling slug deduplication: keyed by parent section-list index
    sibling_seen: dict[int, dict[str, int]] = {0: {}}

    # Hierarchical address prefix: keyed by section-list index
    # For the root the "fragment path" is empty.
    idx_to_frag: dict[int, str] = {0: ''}

    for i, h in enumerate(headings):
        start, end = spans[i]

        # Determine parent: the nearest ancestor level < h.level
        parent_level = h.level - 1
        while parent_level > 0 and parent_level not in level_to_idx:
            parent_level -= 1
        parent_idx = level_to_idx.get(parent_level, 0)

        # Slug deduplication within sibling group (same parent)
        if parent_idx not in sibling_seen:
            sibling_seen[parent_idx] = {}
        raw_slug = slugify(h.text)
        slug = _resolve_slug(raw_slug, sibling_seen[parent_idx])

        # Build hierarchical fragment
        parent_frag = idx_to_frag[parent_idx]
        frag = f'{parent_frag}/{slug}' if parent_frag else slug
        address = f'{doc_name}#{frag}'

        # Content: raw source lines for this section (inclusive, 0-based)
        content = ''.join(source_lines[start:end + 1])

        section = Section(
            doc_id=0,
            address=address,
            heading=h.text,
            slug=slug,
            level=h.level,
            start_line=start,
            end_line=end,
            content=content,
            estimated_tokens=estimate_tokens(content),
        )
        sections.append(section)

        my_idx = len(sections) - 1
        level_to_idx[h.level] = my_idx
        idx_to_frag[my_idx] = frag

        # Invalidate all deeper levels so they don't bleed into siblings
        for lvl in list(level_to_idx.keys()):
            if lvl > h.level:
                del level_to_idx[lvl]

    return sections


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_text(text: str, doc_path: str = "test.md") -> list[Section]:
    """Parse Markdown source *text* and return a flat list of Section objects.

    *doc_path* is used as the prefix for all section addresses
    (e.g. ``"docs/guide.md#introduction"``).

    The returned list is ordered depth-first; element 0 is always the L0
    document root (level=0).
    """
    # 1. Strip YAML front matter
    stripped_text, fm_offset = _strip_frontmatter(text)

    # 2. Split original text into lines for content extraction
    #    We keep the original source lines (with front matter) so that the
    #    L0 root content equals the full file text, and heading sections
    #    reference the correct original lines.
    original_lines = text.splitlines(keepends=True)

    # 3. Extract headings from stripped text (correct heading detection)
    headings = _extract_headings(stripped_text)

    # 4. Build section tree
    return _build_sections(headings, original_lines, doc_path, fm_offset)


def parse_file(path: str) -> list[Section]:
    """Parse a Markdown file and return a flat list of Section objects.

    The list is ordered depth-first (parent before children).
    Section 0 is always the L0 document root (level=0).
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_text(text, Path(path).name)
