"""Text and JSON rendering for pctx output.

Implements formatting for ls, outline, and show commands,
including token estimation, depth-limited child stubs,
and hierarchical truncation.
"""

from __future__ import annotations

import json
from typing import Optional

from pctx.models import Document, Section
from pctx.parser import estimate_tokens


# ---------------------------------------------------------------------------
# Truncation helpers
# ---------------------------------------------------------------------------

def truncate_content(
    content: str, max_tokens: int
) -> tuple[str, bool]:
    """Truncate content to respect max_tokens.

    Priority:
      1. Include complete paragraphs
      2. If a single paragraph exceeds the budget, truncate at word/line boundary
    Returns (truncated_content, was_truncated).
    """
    if estimate_tokens(content) <= max_tokens:
        return content, False

    paragraphs = content.split("\n\n")
    included_paras: list[str] = []
    current_tokens = 0

    for p in paragraphs:
        p_with_sep = (p + "\n\n") if included_paras else p
        p_tokens = estimate_tokens(p_with_sep)
        if current_tokens + p_tokens <= max_tokens:
            included_paras.append(p)
            current_tokens += p_tokens
        else:
            break

    if included_paras:
        return "\n\n".join(included_paras).strip(), True

    # Even the first paragraph exceeds max_tokens: truncate lines
    lines = content.splitlines()
    included_lines: list[str] = []
    line_tokens = 0
    for line in lines:
        l_tokens = estimate_tokens(line + "\n")
        if line_tokens + l_tokens <= max_tokens:
            included_lines.append(line)
            line_tokens += l_tokens
        else:
            break

    if included_lines:
        return "\n".join(included_lines).strip(), True

    # Fallback to byte slice
    max_bytes = max(1, max_tokens * 4)
    raw = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    return raw.strip(), True


# ---------------------------------------------------------------------------
# LS rendering
# ---------------------------------------------------------------------------

def render_ls_text(
    documents: list[Document],
    token_counts: Optional[dict[str, int]] = None,
) -> str:
    """Render documents list as clean compact text."""
    if not documents:
        return "No documents indexed."

    token_counts = token_counts or {}
    lines = []
    for doc in documents:
        tokens_str = f" (~{token_counts[doc.path]} tokens)" if doc.path in token_counts else ""
        summary_str = f"  {doc.summary}" if doc.summary else ""
        lines.append(f"{doc.path}{tokens_str}{summary_str}")

    return "\n".join(lines)


def render_ls_json(
    documents: list[Document],
    token_counts: Optional[dict[str, int]] = None,
) -> str:
    """Render documents list as JSON."""
    token_counts = token_counts or {}
    items = []
    for doc in documents:
        item = {
            "path": doc.path,
            "summary": doc.summary,
        }
        if doc.path in token_counts:
            item["estimated_tokens"] = token_counts[doc.path]
        items.append(item)
    return json.dumps(items, indent=2)


# ---------------------------------------------------------------------------
# OUTLINE rendering
# ---------------------------------------------------------------------------

def render_outline_text(
    sections: list[Section],
    depth: Optional[int] = None,
) -> str:
    """Render heading hierarchy with addresses and token estimates."""
    lines = []
    # Filter out L0 root
    headings = [s for s in sections if s.level > 0]
    if depth is not None:
        headings = [s for s in headings if s.level <= depth]

    if not headings:
        return "No headings found."

    for s in headings:
        indent = "  " * (s.level - 1)
        prefix = "#" * s.level
        heading_text = s.heading or "(untitled)"
        lines.append(f"{indent}{prefix} {heading_text}  [{s.address}]  (~{s.estimated_tokens} tokens)")

    return "\n".join(lines)


def render_outline_json(
    sections: list[Section],
    depth: Optional[int] = None,
) -> str:
    """Render heading hierarchy as JSON."""
    headings = [s for s in sections if s.level > 0]
    if depth is not None:
        headings = [s for s in headings if s.level <= depth]

    items = [
        {
            "address": s.address,
            "heading": s.heading,
            "level": s.level,
            "estimated_tokens": s.estimated_tokens,
            "start_line": s.start_line,
            "end_line": s.end_line,
        }
        for s in headings
    ]
    return json.dumps(items, indent=2)


# ---------------------------------------------------------------------------
# SHOW rendering
# ---------------------------------------------------------------------------

def render_show_text(
    section: Section,
    all_sections: list[Section],
    depth: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Render section content in text mode with depth stubs and truncation."""
    # Find child sections belonging to this section
    # A section is a descendant if its level > section.level and its line span is within section
    children = [
        s
        for s in all_sections
        if s.level > section.level and s.start_line >= section.start_line and s.end_line <= section.end_line
    ]

    stubs: list[Section] = []
    content_to_render = section.content

    if depth is not None:
        # Cut content at the start of any child section whose relative depth > depth
        # Relative depth of child = child.level - section.level (or level directly if section.level == 0)
        base_level = section.level
        cutoff_line: Optional[int] = None

        for child in children:
            rel_depth = child.level - base_level if base_level > 0 else child.level
            if rel_depth > depth:
                if cutoff_line is None or child.start_line < cutoff_line:
                    cutoff_line = child.start_line

        if cutoff_line is not None:
            # Lines in section.content are relative to section.start_line
            # Slice section.content to only include lines before cutoff_line
            rel_cut = cutoff_line - section.start_line
            content_lines = section.content.splitlines(keepends=True)
            content_to_render = "".join(content_lines[:rel_cut]).rstrip()

            # Children that were stubbed out (immediate children at depth+1)
            target_rel_depth = depth + 1
            stubs = [
                c for c in children
                if (c.level - base_level if base_level > 0 else c.level) == target_rel_depth
            ]

    # Truncate content if max_tokens is provided
    continuation_address: Optional[str] = None
    was_truncated = False

    if max_tokens is not None:
        content_to_render, was_truncated = truncate_content(content_to_render, max_tokens)
        if was_truncated:
            # If stubs exist, continuation points to first stub; otherwise to the section itself
            continuation_address = stubs[0].address if stubs else section.address

    output_parts = [content_to_render.rstrip()]

    if was_truncated:
        output_parts.append("\n\n[TRUNCATED]")
        if continuation_address:
            output_parts.append(f"\nContinue from: {continuation_address}")

    if stubs:
        output_parts.append("\n\nSub-sections:")
        for stub in stubs:
            output_parts.append(
                f"\n  → {stub.address}  {stub.heading or ''}  (~{stub.estimated_tokens} tokens)"
            )

    return "".join(output_parts)


def render_show_json(
    section: Section,
    all_sections: list[Section],
    depth: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """Render section content as JSON with stubs and truncation metadata."""
    children = [
        s
        for s in all_sections
        if s.level > section.level and s.start_line >= section.start_line and s.end_line <= section.end_line
    ]

    stubs: list[Section] = []
    content_to_render = section.content

    if depth is not None:
        base_level = section.level
        cutoff_line: Optional[int] = None

        for child in children:
            rel_depth = child.level - base_level if base_level > 0 else child.level
            if rel_depth > depth:
                if cutoff_line is None or child.start_line < cutoff_line:
                    cutoff_line = child.start_line

        if cutoff_line is not None:
            rel_cut = cutoff_line - section.start_line
            content_lines = section.content.splitlines(keepends=True)
            content_to_render = "".join(content_lines[:rel_cut]).rstrip()

            target_rel_depth = depth + 1
            stubs = [
                c for c in children
                if (c.level - base_level if base_level > 0 else c.level) == target_rel_depth
            ]

    continuation_address: Optional[str] = None
    was_truncated = False

    if max_tokens is not None:
        content_to_render, was_truncated = truncate_content(content_to_render, max_tokens)
        if was_truncated:
            continuation_address = stubs[0].address if stubs else section.address

    data = {
        "address": section.address,
        "heading": section.heading,
        "level": section.level,
        "estimated_tokens": estimate_tokens(content_to_render),
        "content": content_to_render,
        "truncated": was_truncated,
        "continuation_address": continuation_address,
        "stubs": [
            {
                "address": s.address,
                "heading": s.heading,
                "level": s.level,
                "estimated_tokens": s.estimated_tokens,
            }
            for s in stubs
        ],
    }
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# SEARCH rendering
# ---------------------------------------------------------------------------

def render_search_text(results: list[dict]) -> str:
    """Render search results as text."""
    if not results:
        return "No results found."

    lines = []
    for r in results:
        heading_part = f"  {r['heading']}" if r.get("heading") else ""
        lines.append(f"{r['address']}{heading_part}")
        if r.get("snippet"):
            snippet = r["snippet"].replace("<b>", "**").replace("</b>", "**")
            lines.append(f"  {snippet}")
        lines.append("")

    return "\n".join(lines).rstrip()


def render_search_json(results: list[dict]) -> str:
    """Render search results as JSON."""
    return json.dumps(results, indent=2)
