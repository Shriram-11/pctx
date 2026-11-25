"""Tests for full-text search (Phase 6)."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

from pctx.index import Index

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def search_env():
    """Create a temporary directory with indexed fixture files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for f in FIXTURES_DIR.glob("*.md"):
            shutil.copy(f, tmp_path / f.name)

        idx = Index.for_root(tmp_path)
        idx.index_directory(tmp_path)
        idx.close()
        yield tmp_path


def run_cli(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "pctx"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_search_heading_ranks_above_body():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # File 1 has "Widget" in heading
        (tmp_path / "heading_match.md").write_text(
            "# Widget\n\nSome unrelated documentation content.\n", encoding="utf-8"
        )
        # File 2 has "Widget" only in body
        (tmp_path / "body_match.md").write_text(
            "# Overview\n\nThis system implements a widget component.\n", encoding="utf-8"
        )

        idx = Index.for_root(tmp_path)
        idx.index_directory(tmp_path)
        results = idx.search("widget")
        idx.close()

        assert len(results) >= 2
        # First result should be the heading match
        assert results[0]["address"].startswith("heading_match.md")


def test_search_valid_addresses(search_env):
    idx = Index.for_root(search_env)
    results = idx.search("Prerequisites")
    idx.close()

    assert len(results) > 0
    for r in results:
        addr = r["address"]
        assert ".md" in addr
        # Must be retrievable
        with Index.for_root(search_env) as index:
            sec = index.get_section(addr)
            assert sec is not None


def test_search_snippets(search_env):
    idx = Index.for_root(search_env)
    results = idx.search("Prerequisites")
    idx.close()

    assert len(results) > 0
    top = results[0]
    assert "<b>" in top["snippet"]
    assert "</b>" in top["snippet"]


def test_search_empty_and_whitespace(search_env):
    idx = Index.for_root(search_env)
    assert idx.search("") == []
    assert idx.search("   ") == []
    assert idx.search("\t\n") == []
    idx.close()

    # CLI test
    res = run_cli("search", "", cwd=search_env)
    assert res.returncode == 0
    assert "No results found." in res.stdout


def test_search_malformed_queries(search_env):
    idx = Index.for_root(search_env)
    # Special FTS characters should not raise errors
    special_queries = ['"', "'''", "*", "(", ")", "AND OR NOT", ":::*", '"""""']
    for q in special_queries:
        res = idx.search(q)
        assert isinstance(res, list)
    idx.close()


def test_search_after_modify(search_env):
    idx = Index.for_root(search_env)
    # Before modification: "ZebraElephantUnicorn" does not exist
    assert idx.search("ZebraElephantUnicorn") == []

    # Modify file
    target = search_env / "basic.md"
    content = target.read_text(encoding="utf-8")
    target.write_text(content + "\n\n## ZebraElephantUnicorn\n\nUnique animal.\n", encoding="utf-8")

    idx.index_directory(search_env)
    results = idx.search("ZebraElephantUnicorn")
    idx.close()

    assert len(results) >= 1
    assert "zebraelephantunicorn" in results[0]["address"]


def test_search_after_delete(search_env):
    idx = Index.for_root(search_env)
    # Target "setext" which is in setext.md
    assert len(idx.search("setext")) > 0

    # Delete setext.md
    (search_env / "setext.md").unlink()
    idx.index_directory(search_env)

    results = idx.search("setext")
    idx.close()

    assert len(results) == 0


def test_search_cli_json(search_env):
    res = run_cli("search", "Getting", "--json", cwd=search_env)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "address" in first
    assert "heading" in first
    assert "snippet" in first
    assert "score" in first


def test_search_cli_text_format(search_env):
    res = run_cli("search", "Prerequisites", cwd=search_env)
    assert res.returncode == 0
    assert "basic.md" in res.stdout
    assert "Prerequisites" in res.stdout
    assert "**" in res.stdout
    assert "<b>" not in res.stdout
    assert "</b>" not in res.stdout


def test_search_cli_json_keeps_html_markers(search_env):
    res = run_cli("search", "Prerequisites", "--json", cwd=search_env)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert len(data) > 0
    assert "<b>" in data[0]["snippet"]
    assert "</b>" in data[0]["snippet"]


def test_search_body_match_includes_heading(search_env):
    res = run_cli("search", "Python", cwd=search_env)
    assert res.returncode == 0
    # "Python 3.10+" is in the body of Prerequisites
    assert "Prerequisites" in res.stdout


def test_search_in_document_and_directory():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "api.md").write_text("# API\n\nRate limiting rules.\n", encoding="utf-8")
        (tmp_path / "docs" / "guide.md").write_text("# Guide\n\nRate limiting examples.\n", encoding="utf-8")
        (tmp_path / "other.md").write_text("# Other\n\nRate limiting notes.\n", encoding="utf-8")

        idx = Index.for_root(tmp_path)
        idx.index_directory(tmp_path)

        # Single file scope
        api_only = idx.search("rate", doc_scope="docs/api.md")
        assert len(api_only) > 0
        assert all(r["address"].startswith("docs/api.md") for r in api_only)

        # Directory scope with trailing slash
        docs_dir = idx.search("rate", doc_scope="docs/")
        assert len(docs_dir) >= 2
        assert all(r["address"].startswith("docs/") for r in docs_dir)
        assert not any(r["address"].startswith("other.md") for r in docs_dir)

        # Directory scope without trailing slash
        docs_no_slash = idx.search("rate", doc_scope="docs")
        assert len(docs_no_slash) >= 2
        assert all(r["address"].startswith("docs/") for r in docs_no_slash)
        idx.close()

        # CLI --in flag
        res = run_cli("search", "rate", "--in", "docs/api.md", "--json", cwd=tmp_path)
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert len(data) > 0
        assert all(item["address"].startswith("docs/api.md") for item in data)


def test_search_prefix_matching():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "auth.md").write_text(
            "# Authentication\n\nToken authorization and authenticator setup.\n",
            encoding="utf-8",
        )

        idx = Index.for_root(tmp_path)
        idx.index_directory(tmp_path)

        # Without prefix, "auth" does not match "Authentication"
        assert idx.search("auth") == []

        # With prefix, "auth" matches
        results = idx.search("auth", prefix=True)
        assert len(results) > 0
        assert results[0]["match_kind"] == "prefix"

        # Exact match still reports match_kind == "exact"
        exact_results = idx.search("Authentication")
        assert len(exact_results) > 0
        assert exact_results[0]["match_kind"] == "exact"
        idx.close()

        # CLI --prefix
        res = run_cli("search", "auth", "--prefix", "--json", cwd=tmp_path)
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert len(data) > 0
        assert data[0]["match_kind"] == "prefix"


def test_search_dedup_suppresses_redundant_parent():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "doc.md").write_text(
            "# Guide\n\nGeneral introduction.\n\n## Rate Limiting\n\nConfigure rate limiting quotas.\n",
            encoding="utf-8",
        )

        idx = Index.for_root(tmp_path)
        idx.index_directory(tmp_path)

        # With dedup=True (default), child "Rate Limiting" has heading match (higher score)
        # so parent "# Guide" and L0 "doc.md" are suppressed.
        deduped = idx.search("limiting")
        addrs = [r["address"] for r in deduped]
        assert "doc.md#guide/rate-limiting" in addrs
        assert "doc.md#guide" not in addrs
        assert "doc.md" not in addrs

        # With dedup=False, parent sections are included
        raw = idx.search("limiting", dedup=False)
        raw_addrs = [r["address"] for r in raw]
        assert "doc.md#guide/rate-limiting" in raw_addrs
        assert "doc.md#guide" in raw_addrs
        idx.close()

        # CLI --no-dedup
        res = run_cli("search", "limiting", "--no-dedup", "--json", cwd=tmp_path)
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert any(r["address"] == "doc.md#guide" for r in data)


def test_search_pagination():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for i in range(5):
            (tmp_path / f"doc{i}.md").write_text(
                f"# Section {i}\n\nAuthentication token details {i}.\n",
                encoding="utf-8",
            )

        with Index.for_root(tmp_path) as idx:
            idx.index_directory(tmp_path)

            page1, total1 = idx.search_paginated("Authentication", limit=2, offset=0)
            page2, total2 = idx.search_paginated("Authentication", limit=2, offset=2)
            assert len(page1) == 2
            assert len(page2) == 2
            assert total1 == 5
            assert total2 == 5
            assert page1[0]["address"] != page2[0]["address"]

        # CLI --limit and --offset with --json
        res = run_cli("search", "Authentication", "--limit", "2", "--offset", "2", "--json", cwd=tmp_path)
        assert res.returncode == 0
        payload = json.loads(res.stdout)
        assert payload["total_hits"] == 5
        assert payload["offset"] == 2
        assert len(payload["results"]) == 2


def test_search_fuzzy_matching():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "guide.md").write_text(
            "# Authentication\n\nConfigure token verification.\n\n## Configuration\n\nSettings.\n",
            encoding="utf-8",
        )

        with Index.for_root(tmp_path) as idx:
            idx.index_directory(tmp_path)

            # Exact search still returns exact results unchanged
            exact = idx.search("Authentication", fuzzy=True)
            assert len(exact) > 0
            assert exact[0]["match_kind"] == "exact"

            # Single-character typo in heading-only match ("Authenticaiton" -> "Authentication")
            typo1 = idx.search("Authenticaiton", fuzzy=True)
            assert len(typo1) > 0
            assert typo1[0]["match_kind"] == "fuzzy"
            assert typo1[0]["matched_term"] == "authentication"

            # Two-character typo for long terms (>= 8 chars): "authentcaton" -> "authentication"
            typo2 = idx.search("authentcaton", fuzzy=True)
            assert len(typo2) > 0
            assert typo2[0]["match_kind"] == "fuzzy"
            assert typo2[0]["matched_term"] == "authentication"

            # Completely wrong query returns empty even with fuzzy
            assert idx.search("zzzzzzzzzz", fuzzy=True) == []

        # CLI --fuzzy text & JSON
        res_text = run_cli("search", "autentication", "--fuzzy", cwd=tmp_path)
        assert res_text.returncode == 0
        assert "fuzzy match" in res_text.stdout
        assert "authentication" in res_text.stdout

        res_json = run_cli("search", "autentication", "--fuzzy", "--json", cwd=tmp_path)
        assert res_json.returncode == 0
        data = json.loads(res_json.stdout)
        assert len(data) > 0
        assert data[0]["match_kind"] == "fuzzy"
        assert data[0]["matched_term"] == "authentication"
