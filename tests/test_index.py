"""Tests for pctx.index — SQLite and FTS5 indexing."""

import shutil
import tempfile
from pathlib import Path
import pytest

from pctx.index import Index, IndexNotFoundError
from pctx.models import Document, Section

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def temp_docs_dir():
    """Create a temporary directory with copies of fixtures for indexing tests."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Copy markdown fixtures
        for f in FIXTURES_DIR.glob("*.md"):
            shutil.copy(f, tmp_path / f.name)
        yield tmp_path


def test_init_db(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    conn = idx._get_conn()
    tables = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    ]
    idx.close()
    assert "documents" in tables
    assert "sections" in tables
    assert "sections_fts" in tables


def test_index_directory_first_run(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    stats = idx.index_directory(temp_docs_dir)
    idx.close()

    assert stats["added"] > 0
    assert stats["updated"] == 0
    assert stats["unchanged"] == 0
    assert stats["deleted"] == 0

    # Verify documents in index
    with Index.for_root(temp_docs_dir) as index:
        docs = index.get_documents()
        assert len(docs) == stats["added"]
        paths = [d.path for d in docs]
        assert "basic.md" in paths
        assert "nested.md" in paths


def test_incremental_skip_unchanged(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    stats1 = idx.index_directory(temp_docs_dir)
    total_files = stats1["added"]

    # Second run without changes
    stats2 = idx.index_directory(temp_docs_dir)
    idx.close()

    assert stats2["added"] == 0
    assert stats2["updated"] == 0
    assert stats2["unchanged"] == total_files
    assert stats2["deleted"] == 0


def test_modified_file_updates(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    idx.index_directory(temp_docs_dir)

    # Modify one file
    target = temp_docs_dir / "basic.md"
    original_content = target.read_text(encoding="utf-8")
    target.write_text(original_content + "\n\n## Brand New Section\n\nNew info.\n", encoding="utf-8")

    stats = idx.index_directory(temp_docs_dir)
    idx.close()

    assert stats["added"] == 0
    assert stats["updated"] == 1
    assert stats["unchanged"] > 0
    assert stats["deleted"] == 0

    with Index.for_root(temp_docs_dir) as index:
        sec = index.get_section("basic.md#introduction/brand-new-section")
        assert sec is not None
        assert sec.heading == "Brand New Section"


def test_deleted_file_removes_records(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    idx.index_directory(temp_docs_dir)

    # Delete one file
    target = temp_docs_dir / "no-headings.md"
    target.unlink()

    stats = idx.index_directory(temp_docs_dir)
    idx.close()

    assert stats["deleted"] == 1

    with Index.for_root(temp_docs_dir) as index:
        doc = index.get_document("no-headings.md")
        assert doc is None
        sec = index.get_section("no-headings.md")
        assert sec is None


def test_get_sections_hierarchy(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    idx.index_directory(temp_docs_dir)

    sections = idx.get_sections("basic.md")
    idx.close()

    assert len(sections) >= 5
    root_sec = sections[0]
    assert root_sec.level == 0
    assert root_sec.address == "basic.md"
    assert root_sec.parent_id is None

    # Check child section has parent_id set to root section
    h1 = next(s for s in sections if s.heading == "Introduction")
    assert h1.parent_id == root_sec.id

    # Check H2 section has parent_id set to H1
    h2 = next(s for s in sections if s.heading == "Getting Started")
    assert h2.parent_id == h1.id


def test_get_children(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    idx.index_directory(temp_docs_dir)

    sections = idx.get_sections("basic.md")
    h1 = next(s for s in sections if s.heading == "Introduction")
    children = idx.get_children(h1.id)
    idx.close()

    child_headings = [c.heading for c in children]
    assert "Getting Started" in child_headings
    assert "Configuration" in child_headings


def test_find_index(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    idx.index_directory(temp_docs_dir)
    idx.close()

    # Subdirectory
    sub = temp_docs_dir / "subdir" / "deep"
    sub.mkdir(parents=True)

    found = Index.find(sub)
    assert found.db_path == temp_docs_dir / ".pctx" / "index.sqlite"

    # Nonexistent index raises IndexNotFoundError
    with tempfile.TemporaryDirectory() as empty_dir:
        with pytest.raises(IndexNotFoundError):
            Index.find(empty_dir)


def test_search_fts5(temp_docs_dir):
    idx = Index.for_root(temp_docs_dir)
    idx.index_directory(temp_docs_dir)

    results = idx.search("Prerequisites")
    idx.close()

    assert len(results) > 0
    top = results[0]
    assert "basic.md" in top["address"]
    assert "Prerequisites" in top["heading"]
    assert "snippet" in top
    assert "score" in top


def test_failed_indexing_transaction(temp_docs_dir, monkeypatch):
    idx = Index.for_root(temp_docs_dir)
    idx.index_directory(temp_docs_dir)

    # Count sections before
    sections_before = len(idx.get_sections("basic.md"))

    # Force a failure during section insertion
    def fail_parse(text, doc_path):
        raise RuntimeError("Parsing crashed!")

    monkeypatch.setattr("pctx.index.parse_text", fail_parse)

    target = temp_docs_dir / "basic.md"
    target.write_text("# Modified\n\nContent", encoding="utf-8")

    with pytest.raises(RuntimeError):
        idx.index_file(target, temp_docs_dir)

    idx.close()

    # Re-open and verify database state was not corrupted
    with Index.for_root(temp_docs_dir) as index:
        sections_after = len(index.get_sections("basic.md"))
        assert sections_after == sections_before

