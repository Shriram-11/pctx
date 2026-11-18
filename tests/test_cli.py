"""Integration tests for the pctx CLI."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def indexed_env():
    """Create a temporary directory with indexed fixture files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for f in FIXTURES_DIR.glob("*.md"):
            shutil.copy(f, tmp_path / f.name)

        # Run pctx index
        res = subprocess.run(
            [sys.executable, "-m", "pctx", "index", str(tmp_path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0
        yield tmp_path


def run_pctx(*args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "pctx"] + list(args),
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def test_help():
    res = run_pctx("--help")
    assert res.returncode == 0
    assert "pctx" in res.stdout
    assert "index" in res.stdout
    assert "ls" in res.stdout
    assert "outline" in res.stdout
    assert "show" in res.stdout
    assert "search" in res.stdout


def test_subcommand_helps():
    for subcmd in ["index", "ls", "outline", "show", "search"]:
        res = run_pctx(subcmd, "--help")
        assert res.returncode == 0


def test_no_index_error():
    with tempfile.TemporaryDirectory() as empty_dir:
        res = run_pctx("ls", cwd=empty_dir)
        assert res.returncode == 1
        assert "Error:" in res.stderr
        assert "No pctx index found" in res.stderr


def test_index_command():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shutil.copy(FIXTURES_DIR / "basic.md", tmp_path / "basic.md")

        res = run_pctx("index", str(tmp_path), cwd=tmp_path)
        assert res.returncode == 0
        assert (tmp_path / ".pctx" / "index.sqlite").is_file()
        assert "Indexed" in res.stderr


def test_index_json():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        shutil.copy(FIXTURES_DIR / "basic.md", tmp_path / "basic.md")

        res = run_pctx("index", str(tmp_path), "--json", cwd=tmp_path)
        assert res.returncode == 0
        data = json.loads(res.stdout)
        assert data["added"] == 1


def test_ls(indexed_env):
    res = run_pctx("ls", cwd=indexed_env)
    assert res.returncode == 0
    assert "basic.md" in res.stdout
    assert "nested.md" in res.stdout


def test_ls_json(indexed_env):
    res = run_pctx("ls", "--json", cwd=indexed_env)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert any(d["path"] == "basic.md" for d in data)


def test_outline(indexed_env):
    res = run_pctx("outline", "basic.md", cwd=indexed_env)
    assert res.returncode == 0
    assert "Introduction" in res.stdout
    assert "Getting Started" in res.stdout
    assert "basic.md#introduction" in res.stdout


def test_outline_depth(indexed_env):
    res = run_pctx("outline", "basic.md", "--depth", "1", cwd=indexed_env)
    assert res.returncode == 0
    assert "Introduction" in res.stdout
    assert "Getting Started" not in res.stdout


def test_outline_json(indexed_env):
    res = run_pctx("outline", "basic.md", "--json", cwd=indexed_env)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert any(h["heading"] == "Introduction" for h in data)


def test_show_document_root(indexed_env):
    res = run_pctx("show", "basic.md", cwd=indexed_env)
    assert res.returncode == 0
    assert "# Introduction" in res.stdout


def test_show_section(indexed_env):
    res = run_pctx("show", "basic.md#introduction/getting-started", cwd=indexed_env)
    assert res.returncode == 0
    assert "Getting Started" in res.stdout


def test_show_depth_stubs(indexed_env):
    res = run_pctx("show", "basic.md#introduction", "--depth", "1", cwd=indexed_env)
    assert res.returncode == 0
    assert "Sub-sections:" in res.stdout
    assert "basic.md#introduction/getting-started" in res.stdout


def test_show_max_tokens(indexed_env):
    res = run_pctx("show", "large-section.md", "--max-tokens", "30", cwd=indexed_env)
    assert res.returncode == 0
    assert "[TRUNCATED]" in res.stdout


def test_show_json(indexed_env):
    res = run_pctx("show", "basic.md#introduction", "--json", cwd=indexed_env)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["address"] == "basic.md#introduction"
    assert data["heading"] == "Introduction"
    assert "content" in data


def test_show_nonexistent_section(indexed_env):
    res = run_pctx("show", "basic.md#nonexistent", cwd=indexed_env)
    assert res.returncode == 1
    assert "Error:" in res.stderr


def test_search(indexed_env):
    res = run_pctx("search", "Prerequisites", cwd=indexed_env)
    assert res.returncode == 0
    assert "basic.md" in res.stdout
    assert "Prerequisites" in res.stdout


def test_search_json(indexed_env):
    res = run_pctx("search", "Prerequisites", "--json", cwd=indexed_env)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert isinstance(data, list)
    assert len(data) > 0
    assert any("Prerequisites" in r["heading"] for r in data)
