"""Data models for pctx."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Document:
    path: str           # relative path from index root
    root: str           # absolute path of index root
    content_hash: str   # SHA-256 of file content
    summary: Optional[str] = None
    id: Optional[int] = None


@dataclass
class Section:
    doc_id: int
    address: str        # e.g. "architecture.md#overview/goals"
    heading: Optional[str]
    slug: str
    level: int          # 0=document, 1=H1, 2=H2, etc.
    start_line: int
    end_line: int
    content: str        # raw markdown source
    estimated_tokens: int
    parent_id: Optional[int] = None
    id: Optional[int] = None
    children: list = field(default_factory=list)
