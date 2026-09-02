# SQL command to create the nodes table
CREATE_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY,
    name TEXT,
    kind TEXT,
    file_path TEXT,
    start_line INTEGER,
    end_line INTEGER,
    docstring TEXT,
    source_code TEXT,
    embedding BLOB
);
"""

# SQL command to create the edges table
CREATE_EDGES_TABLE = """
CREATE TABLE IF NOT EXISTS edges (
    source_id TEXT,
    target_id TEXT,
    relation_type TEXT,
    line_number INTEGER,
    UNIQUE(source_id, target_id, relation_type, line_number)
);
"""

# SQL command to track file modifications for incremental builds
CREATE_FILE_MTIME_TABLE = """
CREATE TABLE IF NOT EXISTS file_mtime (
    file_path TEXT PRIMARY KEY,
    mtime REAL
);
"""

# SQL command to store database configuration (like embedding model used)
CREATE_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""