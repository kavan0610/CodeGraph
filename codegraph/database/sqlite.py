import sqlite3
from typing import List, Dict, Any, Optional
from .schema import (
    CREATE_NODES_TABLE, CREATE_EDGES_TABLE, 
    CREATE_FILE_MTIME_TABLE, CREATE_METADATA_TABLE
)
from codegraph.dataclass.symbols import CodeNode, CodeEdge

class GraphStorage:
    """
    Central Data Access Object (DAO) for CodeGraph.
    """
    def __init__(self, db_path: str = "codebase_graph.db"):
        self.db_path = db_path
        self._init_db()

    # 1. CORE DATABASE UTILITIES
    
    def _get_connection(self) -> sqlite3.Connection:
        """Creates a connection with dictionary-like row access."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Helper for SELECT queries returning multiple rows."""
        with self._get_connection() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def _fetch_one(self, query: str, params: tuple = ()) -> Optional[Any]:
        """Helper for SELECT queries returning a single value."""
        with self._get_connection() as conn:
            row = conn.execute(query, params).fetchone()
            return row[0] if row else None

    def _execute(self, query: str, params: tuple = ()):
        """Helper for single INSERT/UPDATE/DELETE queries."""
        with self._get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def _executemany(self, query: str, data: List[tuple]):
        """Helper for bulk INSERT/UPDATE queries."""
        with self._get_connection() as conn:
            conn.executemany(query, data)
            conn.commit()

    def _init_db(self):
        """Initializes schema using constants from schema.py."""
        with self._get_connection() as conn:
            conn.execute(CREATE_NODES_TABLE)
            conn.execute(CREATE_EDGES_TABLE)
            conn.execute(CREATE_FILE_MTIME_TABLE)
            conn.execute(CREATE_METADATA_TABLE)
            conn.commit()

    # 2. INCREMENTAL BUILDER & PARSER (WRITES)

    def insert_nodes(self, nodes: List[CodeNode]):
        query = """
            INSERT OR REPLACE INTO nodes 
            (id, name, kind, file_path, start_line, end_line, docstring, source_code) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        data = [(n.id, n.name, n.kind, n.file_path, n.start_line, n.end_line, n.docstring, n.source_code) for n in nodes]
        self._executemany(query, data)

    def insert_edges(self, edges: List[CodeEdge]):
        query = "INSERT OR IGNORE INTO edges (source_id, target_id, relation_type, line_number) VALUES (?, ?, ?, ?)"
        data = [(e.source_id, e.target_id, e.relation_type, e.line_number) for e in edges]
        self._executemany(query, data)

    def get_all_mtimes(self) -> dict:
        rows = self._fetch_all("SELECT file_path, mtime FROM file_mtime")
        return {row["file_path"]: row["mtime"] for row in rows}

    def upsert_mtimes(self, mtime_data: dict):
        if not mtime_data: return
        query = "INSERT OR REPLACE INTO file_mtime (file_path, mtime) VALUES (?, ?)"
        self._executemany(query, list(mtime_data.items()))

    def remove_stale_files(self, stale_files: list):
        if not stale_files: return
        with self._get_connection() as conn:
            for path in stale_files:
                conn.execute("DELETE FROM edges WHERE source_id IN (SELECT id FROM nodes WHERE file_path = ?)", (path,))
                conn.execute("DELETE FROM nodes WHERE file_path = ?", (path,))
                conn.execute("DELETE FROM file_mtime WHERE file_path = ?", (path,))
            conn.commit()

    def cleanup_dangling_edges(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM edges 
                WHERE source_id NOT IN (SELECT id FROM nodes) OR target_id NOT IN (SELECT id FROM nodes)
            """)
            conn.commit()
            return cursor.rowcount

    # 3. AI VECTOR EMBEDDINGS & METADATA

    def get_metadata(self, key: str) -> Optional[str]:
        return self._fetch_one("SELECT value FROM metadata WHERE key = ?", (key,))

    def set_metadata(self, key: str, value: str):
        self._execute("INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)", (key, value))

    def get_unembedded_nodes(self) -> List[dict]:
        return self._fetch_all("SELECT id, name, kind, file_path, docstring, source_code FROM nodes WHERE embedding IS NULL")

    def get_all_embeddings(self) -> List[dict]:
        return self._fetch_all("SELECT id, name, kind, file_path, start_line, end_line, embedding FROM nodes WHERE embedding IS NOT NULL")

    def update_embeddings(self, node_ids: List[str], embeddings: List[bytes]):
        query = "UPDATE nodes SET embedding = ? WHERE id = ?"
        self._executemany(query, list(zip(embeddings, node_ids)))

    def reset_all_embeddings(self):
        self._execute("UPDATE nodes SET embedding = NULL")

    # 4. GRAPH RESOLUTION & STRUCTURAL QUERIES

    def get_full_graph_data(self) -> dict:
        """Fetches all nodes and edges for rendering the interactive visual graph."""
        with self._get_connection() as conn:
            nodes_rows = [dict(r) for r in conn.execute("SELECT id, name, kind, file_path, start_line, end_line, docstring, source_code FROM nodes").fetchall()]
            edges_rows = [dict(r) for r in conn.execute("SELECT source_id, target_id, relation_type, line_number FROM edges").fetchall()]
        return {"nodes": nodes_rows, "edges": edges_rows}

    def get_lightweight_nodes(self) -> List[dict]:
        """Used by GraphResolver to map out relationships without blowing up RAM."""
        return self._fetch_all("SELECT id, name, kind, file_path, start_line, end_line FROM nodes")

    def get_nodes_by_name(self, name: str) -> List[dict]:
        return self._fetch_all("SELECT id, name, kind, file_path, start_line, end_line, docstring, source_code FROM nodes WHERE name = ?", (name,))

    def get_callers(self, node_id: str) -> List[dict]:
        query = """
            SELECT n.id, n.name, n.kind, n.file_path, e.line_number 
            FROM edges e JOIN nodes n ON e.source_id = n.id 
            WHERE e.target_id = ? AND e.relation_type = 'CALLS'
        """
        return self._fetch_all(query, (node_id,))

    def get_callees(self, node_id: str) -> List[dict]:
        query = """
            SELECT COALESCE(n.name, e.target_id) as name, 
                   COALESCE(n.kind, 'external/unresolved') as kind, 
                   n.file_path, e.line_number, e.target_id
            FROM edges e LEFT JOIN nodes n ON e.target_id = n.id 
            WHERE e.source_id = ? AND e.relation_type = 'CALLS'
        """
        return self._fetch_all(query, (node_id,))

    def get_upstream_neighbors(self, node_id: str) -> List[dict]:
        query = """
            SELECT n.id, n.name, n.kind, e.relation_type
            FROM edges e JOIN nodes n ON e.source_id = n.id
            WHERE e.target_id = ?
        """
        return self._fetch_all(query, (node_id,))

    def get_downstream_neighbors(self, node_id: str) -> List[dict]:
        query = """
            SELECT COALESCE(n.id, e.target_id) as id, 
                   COALESCE(n.name, e.target_id) as name, 
                   COALESCE(n.kind, 'external') as kind, 
                   e.relation_type
            FROM edges e LEFT JOIN nodes n ON e.target_id = n.id
            WHERE e.source_id = ?
        """
        return self._fetch_all(query, (node_id,))