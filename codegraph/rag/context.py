import sqlite3
from typing import Dict, Set
from codegraph.retrieval.structural import StructuralRetriever

class GraphContextBuilder:
    def __init__(self, db_path: str = "codebase_graph.db"):
        self.db_path = db_path
        self.retriever = StructuralRetriever(db_path)

    def _get_nodes_by_ids(self, node_ids: Set[str]) -> Dict[str, Dict]:
        """Fetches the full source code and metadata for a batch of Node IDs."""
        valid_ids = {nid for nid in node_ids if not nid.startswith("unresolved:") and not nid.startswith("ext:")}
        if not valid_ids:
            return {}
            
        placeholders = ",".join("?" * len(valid_ids))
        query = f"SELECT id, name, kind, file_path, docstring, source_code FROM nodes WHERE id IN ({placeholders})"
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, tuple(valid_ids))
            return {row["id"]: dict(row) for row in cursor.fetchall()}

    def build_context(self, target_node_id: str, depth: int = 2) -> str:
        """Builds a massive Markdown context block containing code and relationships."""
        related_ids: Set[str] = {target_node_id}
        relationships_text = []
        
        blast_layers = self.retriever.blast_radius(target_node_id, max_depth=depth)
        for layer_depth, nodes in blast_layers.items():
            for n in nodes:
                related_ids.add(n['id'])
                relationships_text.append(f"[Upstream L{layer_depth}] '{n['name']}' ({n['kind']}) ---> CALLS ---> Target")

        trace_layers = self.retriever.trace(target_node_id, max_depth=depth)
        for layer_depth, nodes in trace_layers.items():
            for n in nodes:
                related_ids.add(n['id'])
                relationships_text.append(f"[Downstream L{layer_depth}] Target ---> CALLS ---> '{n['name']}' ({n['kind']})")

        nodes_data = self._get_nodes_by_ids(related_ids)
        
        blocks = []
        blocks.append("CODEBASE GRAPH CONTEXT\n")
        
        blocks.append("### STRUCTURAL RELATIONSHIPS")
        if not relationships_text:
            blocks.append("No upstream or downstream calls detected.")
        else:
            blocks.append("\n".join(relationships_text))
        
        blocks.append("\n### SOURCE CODE DICTIONARY")
        blocks.append("Below is the full source code for the target node and all related nodes mentioned above.\n")
        
        if target_node_id in nodes_data:
            blocks.append(self._format_node_code(nodes_data[target_node_id], is_target=True))
            related_ids.remove(target_node_id)
            
        for rid in related_ids:
            if rid in nodes_data:
                blocks.append(self._format_node_code(nodes_data[rid]))
                
        return "\n".join(blocks)

    def _format_node_code(self, node: Dict, is_target: bool = False) -> str:
        """Formats a single node into a clean Markdown block."""
        header = f"TARGET: {node['name']}" if is_target else f"RELATED: {node['name']}"
        doc = node.get('docstring') or "No docstring provided."
        code = node.get('source_code') or "# Source code missing."
        
        return f"""
            --- {header} ---
            Type: {node['kind'].upper()}
            File: {node['file_path']}
            Docstring: {doc}
            Code: {code}
        """