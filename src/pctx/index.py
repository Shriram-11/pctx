"""SQLite index stub — manages the .pctx/index.sqlite database."""

# TODO: Implement SQLite index with FTS5


def init_db(db_path: str):
    """Create or open the SQLite database and apply schema migrations."""
    raise NotImplementedError("index.init_db is not yet implemented")


def index_root(root: str, db_path: str):
    """Walk *root*, parse Markdown files, and upsert into the index."""
    raise NotImplementedError("index.index_root is not yet implemented")
