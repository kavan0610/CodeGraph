from typing import List, Dict, Any, Set
from codegraph.database.sqlite import GraphStorage

class StructuralRetriever:
    def __init__(self, db_path: str = "codebase_graph.db"):
        self.storage = GraphStorage(db_path)

    def find_nodes_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Finds all nodes that match an exact name (e.g., 'get_user')."""
        return self.storage.get_nodes_by_name(name)

    def get_callers(self, node_id: str) -> List[Dict[str, Any]]:
        """Finds who calls this node (Upstream)."""
        return self.storage.get_callers(node_id)

    def get_callees(self, node_id: str) -> List[Dict[str, Any]]:
        """Finds who this node calls (Downstream). Includes unresolved external calls."""
        return self.storage.get_callees(node_id)

    def blast_radius(self, node_id: str, max_depth: int = 3) -> Dict[int, List[Dict]]:
        """Walks UP the graph (Callers, Importers) to see what is impacted by changing this node."""
        return self._traverse(node_id, direction="upstream", max_depth=max_depth)

    def trace(self, node_id: str, max_depth: int = 3) -> Dict[int, List[Dict]]:
        """Walks DOWN the graph (Callees) to see execution flow."""
        return self._traverse(node_id, direction="downstream", max_depth=max_depth)

    def _traverse(self, start_id: str, direction: str, max_depth: int) -> Dict[int, List[Dict]]:
        """Breadth-First Search traversal."""
        results = {}
        visited: Set[str] = {start_id}
        current_layer = [start_id]

        for depth in range(1, max_depth + 1):
            next_layer = []
            results[depth] = []

            for current_id in current_layer:
                if direction == "upstream":
                    neighbors = self.storage.get_upstream_neighbors(current_id)
                else:
                    neighbors = self.storage.get_downstream_neighbors(current_id)

                for neighbor in neighbors:
                    n_id = neighbor['id']
                    if n_id not in visited:
                        visited.add(n_id)
                        next_layer.append(n_id)
                        results[depth].append(neighbor)

            current_layer = next_layer
            if not current_layer:
                break

        return results