"""Tests for pctx.render — formatting and truncation."""

import json
import pytest

from pctx.models import Document, Section
from pctx.render import (
    render_ls_json,
    render_ls_text,
    render_outline_json,
    render_outline_text,
    render_show_json,
    render_show_text,
    truncate_content,
)


def make_section(
    address: str,
    heading: str | None,
    level: int,
    start_line: int,
    end_line: int,
    content: str,
    tokens: int = 20,
) -> Section:
    return Section(
        doc_id=1,
        address=address,
        heading=heading,
        slug=address.split("#")[-1] if "#" in address else address,
        level=level,
        start_line=start_line,
        end_line=end_line,
        content=content,
        estimated_tokens=tokens,
    )


def test_ls_text_empty():
    assert "No documents indexed." in render_ls_text([])


def test_ls_text_with_docs():
    docs = [
        Document(path="guide.md", root="/tmp", content_hash="abc", summary="User Guide"),
        Document(path="api.md", root="/tmp", content_hash="def", summary="API Reference"),
    ]
    tokens = {"guide.md": 150, "api.md": 300}
    out = render_ls_text(docs, tokens)
    assert "guide.md (~150 tokens)  User Guide" in out
    assert "api.md (~300 tokens)  API Reference" in out


def test_ls_json():
    docs = [
        Document(path="guide.md", root="/tmp", content_hash="abc", summary="User Guide"),
    ]
    tokens = {"guide.md": 150}
    out = render_ls_json(docs, tokens)
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["path"] == "guide.md"
    assert data[0]["summary"] == "User Guide"
    assert data[0]["estimated_tokens"] == 150


def test_outline_text():
    sections = [
        make_section("doc.md", None, 0, 0, 10, "doc content", 100),
        make_section("doc.md#intro", "Introduction", 1, 0, 10, "# Introduction\n", 50),
        make_section("doc.md#intro/setup", "Setup", 2, 3, 6, "## Setup\n", 25),
        make_section("doc.md#intro/setup/prereqs", "Prerequisites", 3, 5, 6, "### Prerequisites\n", 10),
    ]
    out = render_outline_text(sections)
    assert "# Introduction  [doc.md#intro]  (~50 tokens)" in out
    assert "  ## Setup  [doc.md#intro/setup]  (~25 tokens)" in out
    assert "    ### Prerequisites  [doc.md#intro/setup/prereqs]  (~10 tokens)" in out


def test_outline_text_depth():
    sections = [
        make_section("doc.md", None, 0, 0, 10, "doc content", 100),
        make_section("doc.md#intro", "Introduction", 1, 0, 10, "# Introduction\n", 50),
        make_section("doc.md#intro/setup", "Setup", 2, 3, 6, "## Setup\n", 25),
        make_section("doc.md#intro/setup/prereqs", "Prerequisites", 3, 5, 6, "### Prerequisites\n", 10),
    ]
    out = render_outline_text(sections, depth=2)
    assert "# Introduction" in out
    assert "## Setup" in out
    assert "### Prerequisites" not in out


def test_outline_json():
    sections = [
        make_section("doc.md", None, 0, 0, 10, "doc content", 100),
        make_section("doc.md#intro", "Introduction", 1, 0, 10, "# Introduction\n", 50),
    ]
    out = render_outline_json(sections)
    data = json.loads(out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["address"] == "doc.md#intro"
    assert data[0]["heading"] == "Introduction"
    assert data[0]["level"] == 1
    assert data[0]["estimated_tokens"] == 50


def test_truncate_content_no_truncation():
    text = "Short paragraph."
    content, truncated = truncate_content(text, max_tokens=100)
    assert not truncated
    assert content == text


def test_truncate_content_paragraphs():
    p1 = "Paragraph one with some text."
    p2 = "Paragraph two with some more text."
    p3 = "Paragraph three with even more text."
    full = f"{p1}\n\n{p2}\n\n{p3}"

    # Budget fits p1 and p2, but not p3
    budget = 14
    content, truncated = truncate_content(full, max_tokens=budget)
    assert truncated
    assert p1 in content
    assert p3 not in content


def test_show_text_with_depth_stubs():
    h1_content = (
        "# Introduction\n\n"
        "Welcome.\n\n"
        "## Section A\n\n"
        "Content A.\n\n"
        "## Section B\n\n"
        "Content B.\n"
    )
    h1 = make_section("doc.md#intro", "Introduction", 1, 0, 10, h1_content, 40)
    child_a = make_section("doc.md#intro/a", "Section A", 2, 4, 6, "## Section A\n\nContent A.\n", 15)
    child_b = make_section("doc.md#intro/b", "Section B", 2, 7, 9, "## Section B\n\nContent B.\n", 15)

    all_sections = [h1, child_a, child_b]

    # depth=0: only immediate content of intro, stub child A and child B
    out = render_show_text(h1, all_sections, depth=0)
    assert "Welcome." in out
    assert "Sub-sections:" in out
    assert "→ doc.md#intro/a  Section A" in out
    assert "→ doc.md#intro/b  Section B" in out
    assert "Content A." not in out


def test_show_text_truncation_marker():
    large_content = "\n\n".join(f"Paragraph {i} content text." for i in range(20))
    sec = make_section("doc.md#large", "Large Section", 1, 0, 40, large_content, 200)

    out = render_show_text(sec, [sec], max_tokens=20)
    assert "[TRUNCATED]" in out
    assert "Continue from: doc.md#large" in out


def test_show_json():
    h1 = make_section("doc.md#intro", "Introduction", 1, 0, 5, "# Introduction\n\nWelcome.\n", 20)
    out = render_show_json(h1, [h1])
    data = json.loads(out)
    assert data["address"] == "doc.md#intro"
    assert data["heading"] == "Introduction"
    assert "Welcome." in data["content"]
    assert not data["truncated"]
    assert data["stubs"] == []
