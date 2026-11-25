"""SQLite index management for pctx.

Maintains .pctx/index.sqlite containing document metadata,
section hierarchies, and full-text search index (FTS5).
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pctx.models import Document, Section
from pctx.parser import parse_text


class IndexNotFoundError(Exception):
    """Raised when .pctx/index.sqlite cannot be found."""
    pass


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    root TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    summary TEXT,
    indexed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY,
    doc_id INTEGER NOT NULL,
    parent_id INTEGER,
    address TEXT NOT NULL UNIQUE,
    heading TEXT,
    slug TEXT NOT NULL,
    level INTEGER NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    estimated_tokens INTEGER NOT NULL,
    content TEXT NOT NULL,
    FOREIGN KEY(doc_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY(parent_id) REFERENCES sections(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
    address UNINDEXED,
    heading,
    content
);

CREATE TRIGGER IF NOT EXISTS sections_fts_ai AFTER INSERT ON sections BEGIN
    INSERT INTO sections_fts(rowid, address, heading, content)
    VALUES (new.id, new.address, coalesce(new.heading, ''), new.content);
END;

CREATE TRIGGER IF NOT EXISTS sections_fts_ad AFTER DELETE ON sections BEGIN
    DELETE FROM sections_fts WHERE rowid = old.id;
END;

CREATE TRIGGER IF NOT EXISTS sections_fts_au AFTER UPDATE ON sections BEGIN
    DELETE FROM sections_fts WHERE rowid = old.id;
    INSERT INTO sections_fts(rowid, address, heading, content)
    VALUES (new.id, new.address, coalesce(new.heading, ''), new.content);
END;
"""


def _sha256(text: str) -> str:
    """Compute SHA-256 hex digest for given text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _extract_summary(sections: list[Section], raw_content: str, doc_path: str) -> str:
    """Extract L0 document summary using fallback order:
    1. First H1 heading
    2. First heading of any level
    3. First non-empty paragraph of body text (up to 200 chars)
    4. Document path
    """
    for s in sections:
        if s.level == 1 and s.heading:
            return s.heading.strip()
    for s in sections:
        if s.heading:
            return s.heading.strip()
    for line in raw_content.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return line[:200]
    return doc_path


class Index:
    """Manages SQLite index database at .pctx/index.sqlite."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path).resolve()
        self._conn: Optional[sqlite3.Connection] = None

    def __enter__(self) -> "Index":
        self._get_conn()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.executescript(SCHEMA)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @classmethod
    def for_root(cls, root: str | Path) -> "Index":
        """Create or open Index for specified root directory."""
        root_path = Path(root).resolve()
        pctx_dir = root_path / ".pctx"
        pctx_dir.mkdir(parents=True, exist_ok=True)
        return cls(pctx_dir / "index.sqlite")

    @classmethod
    def find(cls, start_dir: str | Path | None = None) -> "Index":
        """Find .pctx/index.sqlite by walking up from start_dir (default: cwd)."""
        start = Path(start_dir).resolve() if start_dir else Path.cwd().resolve()
        current = start
        while True:
            candidate = current / ".pctx" / "index.sqlite"
            if candidate.is_file():
                return cls(candidate)
            parent = current.parent
            if parent == current:
                break
            current = parent
        raise IndexNotFoundError(
            f"No pctx index found starting from '{start}'. Run 'pctx index <root>' first."
        )

    def index_directory(self, root: str | Path) -> dict[str, int]:
        """Index all Markdown files in root directory.

        Skips hidden files and directories (names starting with '.').
        Removes records for files deleted since last indexing.
        Returns a dict of counts: added, updated, unchanged, deleted.
        """
        root_path = Path(root).resolve()
        stats = {"added": 0, "updated": 0, "unchanged": 0, "deleted": 0}
        found_paths: set[str] = set()

        for md_file in sorted(root_path.rglob("*.md")):
            # Skip hidden files and directories
            rel_parts = md_file.relative_to(root_path).parts
            if any(p.startswith(".") for p in rel_parts):
                continue

            rel_path = md_file.relative_to(root_path).as_posix()
            found_paths.add(rel_path)
            res = self.index_file(md_file, root_path)
            stats[res] += 1

        stats["deleted"] = self.remove_deleted(root_path, found_paths)
        return stats

    def index_file(self, path: str | Path, root: str | Path) -> str:
        """Index a single Markdown file within root.

        Returns 'unchanged', 'updated', or 'added'.
        Performs upsert in a single transaction so partial updates do not occur.
        """
        file_path = Path(path).resolve()
        root_path = Path(root).resolve()
        rel_path = file_path.relative_to(root_path).as_posix()

        content = file_path.read_text(encoding="utf-8")
        content_hash = _sha256(content)

        conn = self._get_conn()
        existing = conn.execute(
            "SELECT id, content_hash FROM documents WHERE path = ? AND root = ?",
            (rel_path, str(root_path)),
        ).fetchone()

        if existing and existing["content_hash"] == content_hash:
            return "unchanged"

        # Parse before opening the transaction so parser errors don't touch DB
        sections = parse_text(content, rel_path)
        summary = _extract_summary(sections, content, rel_path)
        now = datetime.now(timezone.utc).isoformat()

        with conn:
            if existing:
                # Delete old document record — CASCADE deletes sections & FTS trigger cleans FTS
                conn.execute("DELETE FROM documents WHERE id = ?", (existing["id"],))

            cur = conn.execute(
                """INSERT INTO documents (path, root, content_hash, summary, indexed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (rel_path, str(root_path), content_hash, summary, now),
            )
            doc_id = cur.lastrowid

            address_to_id: dict[str, int] = {}
            for sec in sections:
                parent_id: Optional[int] = None
                if sec.level > 0:
                    if "#" in sec.address:
                        doc_part, frag = sec.address.split("#", 1)
                        if "/" in frag:
                            parent_frag = frag.rsplit("/", 1)[0]
                            parent_addr = f"{doc_part}#{parent_frag}"
                        else:
                            parent_addr = doc_part
                        parent_id = address_to_id.get(parent_addr)

                cur_sec = conn.execute(
                    """INSERT INTO sections
                       (doc_id, parent_id, address, heading, slug, level,
                        start_line, end_line, estimated_tokens, content)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        doc_id,
                        parent_id,
                        sec.address,
                        sec.heading,
                        sec.slug,
                        sec.level,
                        sec.start_line,
                        sec.end_line,
                        sec.estimated_tokens,
                        sec.content,
                    ),
                )
                sec_id = cur_sec.lastrowid
                address_to_id[sec.address] = sec_id
                sec.id = sec_id
                sec.doc_id = doc_id
                sec.parent_id = parent_id

        return "updated" if existing else "added"

    def remove_deleted(self, root: str | Path, found_paths: set[str]) -> int:
        """Remove document records for files that no longer exist on disk."""
        conn = self._get_conn()
        root_str = str(Path(root).resolve())
        existing = conn.execute(
            "SELECT id, path FROM documents WHERE root = ?",
            (root_str,),
        ).fetchall()

        deleted = 0
        with conn:
            for row in existing:
                if row["path"] not in found_paths:
                    conn.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
                    deleted += 1
        return deleted

    def get_documents(self) -> list[Document]:
        """Return all indexed documents sorted by path."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, path, root, content_hash, summary FROM documents ORDER BY path"
        ).fetchall()
        return [
            Document(
                id=r["id"],
                path=r["path"],
                root=r["root"],
                content_hash=r["content_hash"],
                summary=r["summary"],
            )
            for r in rows
        ]

    def get_document(self, path: str) -> Optional[Document]:
        """Return Document by relative path, or None."""
        conn = self._get_conn()
        r = conn.execute(
            "SELECT id, path, root, content_hash, summary FROM documents WHERE path = ?",
            (path,),
        ).fetchone()
        if not r:
            return None
        return Document(
            id=r["id"],
            path=r["path"],
            root=r["root"],
            content_hash=r["content_hash"],
            summary=r["summary"],
        )

    def get_sections(self, doc_path: str) -> list[Section]:
        """Return all sections for a document, ordered by start_line."""
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT s.* FROM sections s
               JOIN documents d ON s.doc_id = d.id
               WHERE d.path = ?
               ORDER BY s.start_line, s.level""",
            (doc_path,),
        ).fetchall()
        return [_row_to_section(r) for r in rows]

    def get_section(self, address: str) -> Optional[Section]:
        """Return single section matching given address, or None."""
        conn = self._get_conn()
        r = conn.execute(
            "SELECT * FROM sections WHERE address = ?",
            (address,),
        ).fetchone()
        if not r:
            return None
        return _row_to_section(r)

    def get_children(self, section_id: int) -> list[Section]:
        """Return immediate children of a section."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM sections WHERE parent_id = ? ORDER BY start_line",
            (section_id,),
        ).fetchall()
        return [_row_to_section(r) for r in rows]

    def search(
        self,
        query: str,
        limit: int = 20,
        highlight: tuple[str, str] = ("<b>", "</b>"),
        doc_scope: Optional[str] = None,
        prefix: bool = False,
    ) -> list[dict]:
        """Full-text search over indexed sections using BM25 ranking.

        Headings are weighted 10x higher than body content.
        """
        if not query or not query.strip():
            return []

        conn = self._get_conn()

        # Sanitize query for FTS5: strip dangerous characters or wrap terms in quotes
        clean_terms = []
        for term in query.strip().split():
            clean_term = "".join(c for c in term if c.isalnum() or c in ("-", "_"))
            if clean_term:
                clean_terms.append(f'"{clean_term}"*' if prefix else f'"{clean_term}"')

        if not clean_terms:
            return []

        fts_query = " AND ".join(clean_terms)
        hl_start, hl_end = highlight

        where_clauses = ["sections_fts MATCH ?"]
        params: list[object] = [hl_start, hl_end, fts_query]
        join_sql = ""

        if doc_scope:
            scope = doc_scope.replace("\\", "/")
            if scope.startswith("./"):
                scope = scope[2:]
            escaped = scope.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            join_sql = (
                "JOIN sections s ON s.id = sections_fts.rowid "
                "JOIN documents d ON d.id = s.doc_id"
            )
            if scope.endswith("/"):
                where_clauses.append("d.path LIKE ? ESCAPE '\\'")
                params.append(f"{escaped}%")
            else:
                where_clauses.append("(d.path = ? OR d.path LIKE ? ESCAPE '\\')")
                params.extend([scope, f"{escaped}/%"])

        params.append(limit)
        where_sql = " AND ".join(where_clauses)

        try:
            rows = conn.execute(
                f"""SELECT sections_fts.address, sections_fts.heading,
                           snippet(sections_fts, -1, ?, ?, '...', 30) AS snippet,
                           bm25(sections_fts, 0.0, 10.0, 1.0) AS score
                    FROM sections_fts
                    {join_sql}
                    WHERE {where_sql}
                    ORDER BY score
                    LIMIT ?""",
                tuple(params),
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        match_kind = "prefix" if prefix else "exact"
        return [
            {
                "address": r["address"],
                "heading": r["heading"],
                "snippet": r["snippet"],
                "score": r["score"],
                "match_kind": match_kind,
            }
            for r in rows
        ]


def _row_to_section(row: sqlite3.Row) -> Section:
    return Section(
        id=row["id"],
        doc_id=row["doc_id"],
        parent_id=row["parent_id"],
        address=row["address"],
        heading=row["heading"],
        slug=row["slug"],
        level=row["level"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        estimated_tokens=row["estimated_tokens"],
        content=row["content"],
    )


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path) -> Index:
    """Create or open the SQLite database and apply schema migrations."""
    idx = Index(db_path)
    idx._get_conn()
    return idx


def index_root(root: str | Path, db_path: Optional[str | Path] = None) -> dict[str, int]:
    """Walk root, parse Markdown files, and upsert into the index."""
    idx = Index(db_path) if db_path else Index.for_root(root)
    try:
        return idx.index_directory(root)
    finally:
        idx.close()
