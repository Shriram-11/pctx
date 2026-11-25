"""CLI entry point for pctx."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pctx.index import Index, IndexNotFoundError
from pctx.render import (
    render_ls_json,
    render_ls_text,
    render_outline_json,
    render_outline_text,
    render_search_json,
    render_search_text,
    render_show_json,
    render_show_text,
)


def _get_index() -> Index:
    """Find index or exit with friendly error message."""
    try:
        return Index.find()
    except IndexNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_index(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"Error: Directory '{root}' does not exist.", file=sys.stderr)
        sys.exit(1)

    idx = Index.for_root(root)
    try:
        stats = idx.index_directory(root)
    finally:
        idx.close()

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print(
            f"Indexed {root.name}: {stats['added']} added, {stats['updated']} updated, "
            f"{stats['unchanged']} unchanged, {stats['deleted']} deleted",
            file=sys.stderr,
        )


def cmd_ls(args: argparse.Namespace) -> None:
    idx = _get_index()
    try:
        docs = idx.get_documents()
        token_counts: dict[str, int] = {}
        for d in docs:
            sec = idx.get_section(d.path)
            if sec:
                token_counts[d.path] = sec.estimated_tokens

        if args.json:
            print(render_ls_json(docs, token_counts))
        else:
            print(render_ls_text(docs, token_counts))
    finally:
        idx.close()


def cmd_outline(args: argparse.Namespace) -> None:
    idx = _get_index()
    try:
        # Normalize document path: strip any fragment if provided
        doc_path = args.document.split("#")[0]
        # Normalize backslashes to forward slashes
        doc_path = doc_path.replace("\\", "/")

        sections = idx.get_sections(doc_path)
        if not sections:
            print(f"Error: Document '{doc_path}' not found in index.", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(render_outline_json(sections, depth=args.depth))
        else:
            print(render_outline_text(sections, depth=args.depth))
    finally:
        idx.close()


def cmd_show(args: argparse.Namespace) -> None:
    idx = _get_index()
    try:
        address = args.address.replace("\\", "/")
        section = idx.get_section(address)
        if section is None:
            print(f"Error: Section '{address}' not found in index.", file=sys.stderr)
            sys.exit(1)

        doc_path = address.split("#")[0]
        all_sections = idx.get_sections(doc_path)

        if args.json:
            print(render_show_json(section, all_sections, depth=args.depth, max_tokens=args.max_tokens))
        else:
            print(render_show_text(section, all_sections, depth=args.depth, max_tokens=args.max_tokens))
    finally:
        idx.close()


def cmd_search(args: argparse.Namespace) -> None:
    idx = _get_index()
    try:
        highlight = ("<b>", "</b>") if args.json else ("**", "**")
        limit = args.limit if args.limit is not None else 20
        offset = args.offset if args.offset is not None else 0
        results, total_hits = idx.search_paginated(
            args.query,
            limit=limit,
            offset=offset,
            highlight=highlight,
            doc_scope=args.in_path,
            prefix=args.prefix,
            dedup=not args.no_dedup,
            fuzzy=args.fuzzy,
        )
        if args.json:
            paginated = args.offset is not None or args.limit is not None
            if paginated:
                print(render_search_json(results, total_hits=total_hits, offset=offset))
            else:
                print(render_search_json(results))
        else:
            print(render_search_text(results, query=args.query))
    finally:
        idx.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="pctx",
        description="Index and navigate Markdown documentation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # index
    p_index = subparsers.add_parser("index", help="Build or update the index")
    p_index.add_argument("root", help="Root directory to index")
    p_index.add_argument("--json", action="store_true", help="Output JSON")
    p_index.set_defaults(func=cmd_index)

    # ls
    p_ls = subparsers.add_parser("ls", help="List indexed documents")
    p_ls.add_argument("--json", action="store_true", help="Output JSON")
    p_ls.set_defaults(func=cmd_ls)

    # outline
    p_outline = subparsers.add_parser("outline", help="Display document heading hierarchy")
    p_outline.add_argument("document", help="Document path")
    p_outline.add_argument("--depth", type=int, default=None, help="Limit heading depth")
    p_outline.add_argument("--json", action="store_true", help="Output JSON")
    p_outline.set_defaults(func=cmd_outline)

    # show
    p_show = subparsers.add_parser("show", help="Retrieve section content")
    p_show.add_argument("address", help="Section address (e.g. doc.md#section)")
    p_show.add_argument("--depth", type=int, default=None, help="Limit child expansion depth")
    p_show.add_argument("--max-tokens", type=int, default=None, help="Maximum token budget")
    p_show.add_argument("--json", action="store_true", help="Output JSON")
    p_show.set_defaults(func=cmd_show)

    # search
    p_search = subparsers.add_parser("search", help="Search indexed content")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--in", dest="in_path", default=None, help="Scope search to a document or directory prefix")
    p_search.add_argument("--prefix", action="store_true", help="Enable prefix matching on query terms")
    p_search.add_argument("--fuzzy", action="store_true", help="Enable fuzzy matching fallback on typos")
    p_search.add_argument("--no-dedup", action="store_true", help="Disable parent/child result deduplication")
    p_search.add_argument("--limit", type=int, default=None, help="Maximum results to return (default: 20)")
    p_search.add_argument("--offset", type=int, default=None, help="Number of results to skip (default: 0)")
    p_search.add_argument("--json", action="store_true", help="Output JSON")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
