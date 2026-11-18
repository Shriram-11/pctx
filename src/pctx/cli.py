"""CLI entry point for pctx."""

import argparse
import sys


def cmd_index(args):
    print("index: not implemented yet", file=sys.stderr)
    sys.exit(1)


def cmd_ls(args):
    print("ls: not implemented yet", file=sys.stderr)
    sys.exit(1)


def cmd_outline(args):
    print("outline: not implemented yet", file=sys.stderr)
    sys.exit(1)


def cmd_show(args):
    print("show: not implemented yet", file=sys.stderr)
    sys.exit(1)


def cmd_search(args):
    print("search: not implemented yet", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="pctx",
        description="Index and navigate Markdown documentation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # index
    p_index = subparsers.add_parser("index", help="Build or update the index")
    p_index.add_argument("root", help="Root directory to index")
    p_index.add_argument("--json", action="store_true")
    p_index.set_defaults(func=cmd_index)

    # ls
    p_ls = subparsers.add_parser("ls", help="List indexed documents")
    p_ls.add_argument("--json", action="store_true")
    p_ls.set_defaults(func=cmd_ls)

    # outline
    p_outline = subparsers.add_parser("outline", help="Display document heading hierarchy")
    p_outline.add_argument("document", help="Document path")
    p_outline.add_argument("--json", action="store_true")
    p_outline.set_defaults(func=cmd_outline)

    # show
    p_show = subparsers.add_parser("show", help="Retrieve section content")
    p_show.add_argument("address", help="Section address (e.g. doc.md#section)")
    p_show.add_argument("--depth", type=int, default=None)
    p_show.add_argument("--max-tokens", type=int, default=None)
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    # search
    p_search = subparsers.add_parser("search", help="Search indexed content")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
