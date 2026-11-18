"""
Tests for pctx.parser — fixture-driven specification of expected parser behaviour.

The parser (implemented in Phase 3) must satisfy all assertions here.
Running before Phase 3 is complete will show failures — that is expected.
"""

import pathlib
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def fixture_path(name: str) -> str:
    return str(FIXTURES / name)


def sections_by_address(sections) -> dict:
    """Index a flat section list by address for O(1) look-up in tests."""
    return {s.address: s for s in sections}


# ---------------------------------------------------------------------------
# Import the public API we expect the parser to expose
# ---------------------------------------------------------------------------

from pctx.parser import parse_file, parse_text  # noqa: E402


# ---------------------------------------------------------------------------
# test_basic_structure
# ---------------------------------------------------------------------------

class TestBasicStructure:
    """basic.md — simple H1 / H2 / H3 hierarchy."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("basic.md"))

    def test_returns_list(self, sections):
        assert isinstance(sections, list)
        assert len(sections) > 0

    def test_level_zero_document_section(self, sections):
        """First section is the L0 document root."""
        root = sections[0]
        assert root.level == 0
        assert root.address == "basic.md"

    def test_h1_introduction(self, sections):
        by_addr = sections_by_address(sections)
        sec = by_addr.get("basic.md#introduction")
        assert sec is not None, "Expected section basic.md#introduction"
        assert sec.level == 1
        assert sec.heading == "Introduction"

    def test_h2_getting_started(self, sections):
        by_addr = sections_by_address(sections)
        sec = by_addr.get("basic.md#introduction/getting-started")
        assert sec is not None, "Expected basic.md#introduction/getting-started"
        assert sec.level == 2
        assert sec.heading == "Getting Started"

    def test_h3_prerequisites(self, sections):
        by_addr = sections_by_address(sections)
        sec = by_addr.get("basic.md#introduction/getting-started/prerequisites")
        assert sec is not None, "Expected basic.md#introduction/getting-started/prerequisites"
        assert sec.level == 3
        assert sec.heading == "Prerequisites"

    def test_h2_configuration(self, sections):
        by_addr = sections_by_address(sections)
        sec = by_addr.get("basic.md#introduction/configuration")
        assert sec is not None, "Expected basic.md#introduction/configuration"
        assert sec.level == 2
        assert sec.heading == "Configuration"

    def test_total_section_count(self, sections):
        # L0 + H1 + H2 + H3 + H2 = 5 sections
        assert len(sections) == 5

    def test_all_addresses_unique(self, sections):
        addrs = [s.address for s in sections]
        assert len(addrs) == len(set(addrs)), "All addresses must be unique"


# ---------------------------------------------------------------------------
# test_duplicate_headings
# ---------------------------------------------------------------------------

class TestDuplicateHeadings:
    """duplicate-headings.md — duplicate headings at same level get numeric suffix."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("duplicate-headings.md"))

    def test_first_overview_no_suffix(self, sections):
        by_addr = sections_by_address(sections)
        assert "duplicate-headings.md#document/overview" in by_addr

    def test_first_implementation_no_suffix(self, sections):
        by_addr = sections_by_address(sections)
        assert "duplicate-headings.md#document/implementation" in by_addr

    def test_second_overview_has_suffix(self, sections):
        by_addr = sections_by_address(sections)
        assert "duplicate-headings.md#document/overview-2" in by_addr, (
            "Second occurrence of 'Overview' must become overview-2"
        )

    def test_second_implementation_has_suffix(self, sections):
        by_addr = sections_by_address(sections)
        assert "duplicate-headings.md#document/implementation-2" in by_addr, (
            "Second occurrence of 'Implementation' must become implementation-2"
        )

    def test_all_addresses_unique(self, sections):
        addrs = [s.address for s in sections]
        assert len(addrs) == len(set(addrs))


# ---------------------------------------------------------------------------
# test_setext_headings
# ---------------------------------------------------------------------------

class TestSetextHeadings:
    """setext.md — headings written with === and --- underlines."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("setext.md"))

    def test_h1_detected(self, sections):
        by_addr = sections_by_address(sections)
        sec = by_addr.get("setext.md#top-level-heading")
        assert sec is not None, "Expected setext.md#top-level-heading (H1 via ===)"
        assert sec.level == 1

    def test_h2_detected(self, sections):
        by_addr = sections_by_address(sections)
        sec = by_addr.get("setext.md#top-level-heading/sub-heading")
        assert sec is not None, "Expected setext.md#top-level-heading/sub-heading (H2 via ---)"
        assert sec.level == 2

    def test_heading_text_correct(self, sections):
        by_addr = sections_by_address(sections)
        h1 = by_addr["setext.md#top-level-heading"]
        assert h1.heading == "Top Level Heading"
        h2 = by_addr["setext.md#top-level-heading/sub-heading"]
        assert h2.heading == "Sub Heading"


# ---------------------------------------------------------------------------
# test_frontmatter_skipped
# ---------------------------------------------------------------------------

class TestFrontmatterSkipped:
    """frontmatter.md — YAML front matter must not appear as a section or heading."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("frontmatter.md"))

    def test_no_frontmatter_section(self, sections):
        """The --- delimiters must not produce a heading or section."""
        addrs = [s.address for s in sections]
        for addr in addrs:
            fragment = addr.split("#")[-1] if "#" in addr else ""
            assert "author" not in fragment, (
                f"Front-matter key leaked into address: {addr}"
            )

    def test_h1_main_content_present(self, sections):
        by_addr = sections_by_address(sections)
        assert "frontmatter.md#main-content" in by_addr

    def test_h2_details_present(self, sections):
        by_addr = sections_by_address(sections)
        assert "frontmatter.md#main-content/details" in by_addr

    def test_frontmatter_not_in_content(self, sections):
        """The raw YAML block should not appear inside a heading section's content."""
        by_addr = sections_by_address(sections)
        h1 = by_addr.get("frontmatter.md#main-content")
        if h1:
            assert "title: My Document" not in h1.content


# ---------------------------------------------------------------------------
# test_no_false_headings_in_code
# ---------------------------------------------------------------------------

class TestNoFalseHeadingsInCode:
    """fenced-code.md — # inside fenced code blocks must not be parsed as headings."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("fenced-code.md"))

    def test_only_real_headings(self, sections):
        headings = {s.heading for s in sections if s.heading}
        assert "Real Heading" in headings
        assert "Code Section" in headings
        assert "After Code" in headings
        assert "This is a Python comment, not a heading" not in headings
        assert "Another comment" not in headings

    def test_section_count(self, sections):
        # L0 + H1 + H2 + H2 = 4
        assert len(sections) == 4

    def test_addresses(self, sections):
        by_addr = sections_by_address(sections)
        assert "fenced-code.md#real-heading" in by_addr
        assert "fenced-code.md#real-heading/code-section" in by_addr
        assert "fenced-code.md#real-heading/after-code" in by_addr


# ---------------------------------------------------------------------------
# test_no_headings
# ---------------------------------------------------------------------------

class TestNoHeadings:
    """no-headings.md — document with no headings at all."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("no-headings.md"))

    def test_only_root_section(self, sections):
        """Should return exactly one L0 document section."""
        assert len(sections) == 1

    def test_root_level(self, sections):
        assert sections[0].level == 0

    def test_root_address(self, sections):
        assert sections[0].address == "no-headings.md"

    def test_root_has_content(self, sections):
        """The L0 section should contain all document text."""
        content = sections[0].content
        assert "This document has no headings at all." in content


# ---------------------------------------------------------------------------
# test_line_ranges
# ---------------------------------------------------------------------------

class TestLineRanges:
    """basic.md — verify start_line / end_line are plausible."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("basic.md"))

    def test_start_lines_non_negative(self, sections):
        for sec in sections:
            assert sec.start_line >= 0, f"{sec.address}: start_line must be >= 0"

    def test_end_gte_start(self, sections):
        for sec in sections:
            assert sec.end_line >= sec.start_line, (
                f"{sec.address}: end_line ({sec.end_line}) < start_line ({sec.start_line})"
            )

    def test_root_starts_at_zero(self, sections):
        root = sections[0]
        assert root.start_line == 0

    def test_h1_starts_before_h2(self, sections):
        by_addr = sections_by_address(sections)
        h1 = by_addr["basic.md#introduction"]
        h2 = by_addr["basic.md#introduction/getting-started"]
        assert h1.start_line < h2.start_line

    def test_h2_starts_before_h3(self, sections):
        by_addr = sections_by_address(sections)
        h2 = by_addr["basic.md#introduction/getting-started"]
        h3 = by_addr["basic.md#introduction/getting-started/prerequisites"]
        assert h2.start_line < h3.start_line

    def test_non_overlapping_siblings(self, sections):
        """Sibling sections must not overlap."""
        by_addr = sections_by_address(sections)
        gs = by_addr["basic.md#introduction/getting-started"]
        cfg = by_addr["basic.md#introduction/configuration"]
        assert gs.end_line < cfg.start_line or gs.end_line == cfg.start_line - 1


# ---------------------------------------------------------------------------
# test_source_reconstruction
# ---------------------------------------------------------------------------

class TestSourceReconstruction:
    """basic.md — content slices should reconstruct the original file lines."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("basic.md"))

    @pytest.fixture(scope="class")
    @classmethod
    def raw_lines(cls):
        path = fixture_path("basic.md")
        with open(path, encoding="utf-8") as fh:
            return fh.readlines()

    def test_root_content_matches_file(self, sections, raw_lines):
        """L0 section content must equal full file text."""
        root = sections[0]
        full_text = "".join(raw_lines)
        assert root.content.strip() == full_text.strip()

    def test_heading_text_in_section_content(self, sections):
        """Each section's content must contain its own heading."""
        for sec in sections:
            if sec.heading:
                assert sec.heading in sec.content, (
                    f"{sec.address}: heading '{sec.heading}' not found in content"
                )

    def test_h2_content_contains_its_text(self, sections):
        by_addr = sections_by_address(sections)
        cfg = by_addr["basic.md#introduction/configuration"]
        assert "Configure the tool" in cfg.content


# ---------------------------------------------------------------------------
# test_token_estimation
# ---------------------------------------------------------------------------

class TestTokenEstimation:
    """estimate_tokens helper must be importable and return positive integers."""

    def test_import(self):
        from pctx.parser import estimate_tokens  # noqa: F401

    def test_non_zero(self):
        from pctx.parser import estimate_tokens
        assert estimate_tokens("hello world") > 0

    def test_longer_text_more_tokens(self):
        from pctx.parser import estimate_tokens
        short = estimate_tokens("hi")
        long_ = estimate_tokens("hello world " * 100)
        assert long_ > short

    def test_formula(self):
        """Verify the specified formula: max(1, len(text.encode('utf-8')) // 4)."""
        from pctx.parser import estimate_tokens
        text = "hello"
        expected = max(1, len(text.encode("utf-8")) // 4)
        assert estimate_tokens(text) == expected

    def test_empty_string_returns_one(self):
        from pctx.parser import estimate_tokens
        assert estimate_tokens("") == 1


# ---------------------------------------------------------------------------
# test_parse_text
# ---------------------------------------------------------------------------

class TestParseText:
    """parse_text() must work identically to parse_file() for the same content."""

    def test_basic_via_text(self):
        path = fixture_path("basic.md")
        with open(path, encoding="utf-8") as fh:
            text = fh.read()

        sections = parse_text(text, doc_path="basic.md")
        by_addr = sections_by_address(sections)
        assert "basic.md#introduction" in by_addr
        assert "basic.md#introduction/getting-started" in by_addr

    def test_custom_doc_path(self):
        sections = parse_text("# Hello\n\nworld\n", doc_path="custom/my-doc.md")
        by_addr = sections_by_address(sections)
        assert "custom/my-doc.md#hello" in by_addr

    def test_empty_text(self):
        sections = parse_text("", doc_path="empty.md")
        assert len(sections) >= 1
        assert sections[0].level == 0


# ---------------------------------------------------------------------------
# test_nested
# ---------------------------------------------------------------------------

class TestNestedDocument:
    """nested.md — deep nesting with H4."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("nested.md"))

    def test_h4_deep_level(self, sections):
        by_addr = sections_by_address(sections)
        sec = by_addr.get("nested.md#top-level/section-b/sub-b1/deep-level")
        assert sec is not None, "Expected H4 deep-level section"
        assert sec.level == 4

    def test_all_expected_addresses(self, sections):
        by_addr = sections_by_address(sections)
        expected = [
            "nested.md",
            "nested.md#top-level",
            "nested.md#top-level/section-a",
            "nested.md#top-level/section-a/sub-a1",
            "nested.md#top-level/section-a/sub-a2",
            "nested.md#top-level/section-b",
            "nested.md#top-level/section-b/sub-b1",
            "nested.md#top-level/section-b/sub-b1/deep-level",
        ]
        for addr in expected:
            assert addr in by_addr, f"Missing expected address: {addr}"

    def test_total_count(self, sections):
        assert len(sections) == 8  # L0 + 7 headings


# ---------------------------------------------------------------------------
# test_large_section_tokens
# ---------------------------------------------------------------------------

class TestLargeSectionTokens:
    """large-section.md — token count must be > 0 and reasonably large."""

    @pytest.fixture(scope="class")
    @classmethod
    def sections(cls):
        return parse_file(fixture_path("large-section.md"))

    def test_root_has_tokens(self, sections):
        root = sections[0]
        assert root.estimated_tokens > 0

    def test_h1_has_significant_tokens(self, sections):
        by_addr = sections_by_address(sections)
        h1 = by_addr.get("large-section.md#large-section")
        assert h1 is not None
        assert h1.estimated_tokens > 50

    def test_tokens_match_formula(self, sections):
        """estimated_tokens must equal max(1, len(content.encode('utf-8')) // 4)."""
        for sec in sections:
            expected = max(1, len(sec.content.encode("utf-8")) // 4)
            assert sec.estimated_tokens == expected, (
                f"{sec.address}: expected {expected} tokens, got {sec.estimated_tokens}"
            )
