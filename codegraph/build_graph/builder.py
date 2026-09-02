from typing import List
from codegraph.graph.python_parser import parse_python_file
from codegraph.graph.resolver import GraphResolver
from codegraph.database.sqlite import GraphStorage
from codegraph.graph.diffing_engine import DiffingEngine
from codegraph.dataclass.symbols import CodeNode, CodeEdge

DEFAULT_IGNORE_DIRS = {
    ".git", "__pycache__", "venv", "env", ".venv", 
    "node_modules", ".pytest_cache", "build", "dist"
}

class GraphBuilder:
    def __init__(self, root_dir: str, db_path: str = "codebase_graph.db"):
        self.root_dir = root_dir
        self.db_path = db_path
        self.all_nodes: List[CodeNode] = []
        self.all_edges: List[CodeEdge] = []

    def build(self):
        print(f"Scanning directory: {self.root_dir}")
        storage = GraphStorage(self.db_path)
        differ = DiffingEngine(storage)
        
        to_parse, to_delete, disk_state = differ.get_changed_files(self.root_dir, DEFAULT_IGNORE_DIRS)

        if not to_parse and not to_delete:
            print("Database is already up to date! No changes detected.")
            return

        if to_delete:
            print(f"Removing {len(to_delete)} stale files from database...")
            storage.remove_stale_files(to_delete)

        if to_parse:
            print(f"Parsing {len(to_parse)} new/modified files...")
            successfully_parsed = []
            
            for file_path in to_parse:
                try:
                    nodes, edges = parse_python_file(file_path)
                    self.all_nodes.extend(nodes)
                    self.all_edges.extend(edges)
                    successfully_parsed.append(file_path)
                except Exception as e:
                    print(f"Warning: Failed to parse {file_path}. Error: {e}")

            print(f"Extracted {len(self.all_nodes)} new nodes and {len(self.all_edges)} raw edges.")

            if self.all_nodes:
                print("Loading global context to resolve cross-file edges...")
                
                existing_data = storage.get_lightweight_nodes()
        
                global_nodes = [
                    CodeNode(
                        id=row["id"], 
                        name=row["name"], 
                        kind=row["kind"],
                        file_path=row["file_path"], 
                        start_line=row.get("start_line", 0),
                        end_line=row.get("end_line", 0), 
                        docstring="",
                        source_code=""
                    ) for row in existing_data
                ]
                
                combined_nodes = global_nodes + self.all_nodes

                print("Resolving relationships...")
                resolver = GraphResolver(combined_nodes, self.all_edges)
                resolved_edges = resolver.resolve()

                print(f"Saving to database at {self.db_path}...")
                storage.insert_nodes(self.all_nodes)
                storage.insert_edges(resolved_edges)

                mtimes_to_save = {p: disk_state[p] for p in successfully_parsed}
                storage.upsert_mtimes(mtimes_to_save)
                
                print("Sweeping database for dangling edges...")
                deleted_edges = storage.cleanup_dangling_edges()
                if deleted_edges > 0:
                    print(f"Purged {deleted_edges} orphaned edges pointing to deleted functions.")
        
        print(f"Incremental build complete!")