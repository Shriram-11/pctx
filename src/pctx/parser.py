"""Markdown parser stub — parses Markdown files into Section trees.

Phase 3 will provide the full implementation using markdown-it-py.
The public API surface is defined here so test_parser.py can import
without an ImportError, and so type-checkers can reason about the module.
"""

from __future__ import annotations

from pctx.models import Section


# ---------------------------------------------------------------------------
# Token estimation (spec-defined formula)
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Return a rough token estimate: max(1, utf-8 bytes // 4)."""
    return max(1, len(text.encode("utf-8")) // 4)


# ---------------------------------------------------------------------------
# Public parsing API (stubs — implemented in Phase 3)
# ---------------------------------------------------------------------------

def parse_file(path: str) -> list[Section]:
    """Parse a Markdown file and return a flat list of Section objects.

    The list is ordered depth-first (parent before children).
    Section 0 is always the L0 document root (level=0).
    """
    raise NotImplementedError("parser.parse_file is not yet implemented (Phase 3)")


def parse_text(text: str, doc_path: str = "test.md") -> list[Section]:
    """Parse Markdown source text and return a flat list of Section objects.

    ``doc_path`` is used to build section addresses
    (e.g. ``"docs/guide.md#introduction"``).
    """
    raise NotImplementedError("parser.parse_text is not yet implemented (Phase 3)")
