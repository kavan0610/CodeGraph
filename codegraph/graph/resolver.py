import os
from typing import List, Dict, Optional, Set
from codegraph.dataclass.symbols import CodeNode, CodeEdge

class GraphResolver:
    def __init__(self, nodes: List[CodeNode], edges: List[CodeEdge]):
        self.node_meta: Dict[str, Dict[str, str]] = {
            n.id: {"file_path": n.file_path, "name": n.name, "kind": n.kind} 
            for n in nodes
        }
        
        self.valid_node_ids: Set[str] = set(self.node_meta.keys())
        
        self.nodes = None 
        
        self.edges = edges

        self.module_defs: Dict[str, Dict[str, str]] = {}
        
        self.class_methods: Dict[str, Dict[str, str]] = {}
        
        self.global_symbol_index: Dict[str, List[str]] = {}
        
        self.import_maps: Dict[str, Dict[str, str]] = {}
        
        self._build_indices()

    def _build_indices(self):
        """Index symbols by lexical scope and build cross-file resolution maps."""
        for nid, meta in self.node_meta.items():
            fp = os.path.normpath(meta["file_path"])
            name = meta["name"]
            kind = meta["kind"]
            
            if name not in self.global_symbol_index:
                self.global_symbol_index[name] = []
            self.global_symbol_index[name].append(nid)

            if kind == "method":
                parts = nid.split(":")
                if "class" in parts:
                    class_idx = parts.index("class")
                    class_name = parts[class_idx + 1]
                    if (fp, class_name) not in self.class_methods:
                        self.class_methods[(fp, class_name)] = {}
                    self.class_methods[(fp, class_name)][name] = nid
            elif kind in ("function", "class", "variable", "module"):
                if fp not in self.module_defs:
                    self.module_defs[fp] = {}
                self.module_defs[fp][name] = nid

        for edge in self.edges:
            if edge.relation_type == "IMPORTS":
                source_file = os.path.normpath(edge.source_id.replace("module:", ""))
                if source_file not in self.import_maps:
                    self.import_maps[source_file] = {}
                
                raw_target = edge.target_id.replace("ext:", "")
                local_alias = raw_target.split(".")[-1]
                self.import_maps[source_file][local_alias] = raw_target

    def resolve(self) -> List[CodeEdge]:
        resolved_edges = []
        
        for edge in self.edges:
            target_id = edge.target_id
            
            if edge.relation_type == "CALLS" and edge.target_id.startswith("call:"):
                raw_call = edge.target_id.replace("call:", "")
                target_id = self._resolve_call(edge.source_id, raw_call)
                
            if target_id and target_id in self.valid_node_ids and edge.source_id in self.valid_node_ids:
                resolved_edges.append(CodeEdge(edge.source_id, target_id, edge.relation_type, edge.line_number))
                
        return resolved_edges

    def _resolve_call(self, source_id: str, call_name: str) -> Optional[str]:
        source_meta = self.node_meta.get(source_id)
        if not source_meta:
            return None
            
        fp = os.path.normpath(source_meta["file_path"])

        if call_name.startswith("self."):
            method_name = call_name.split(".")[1]
            parts = source_id.split(":")
            if "class" in parts:
                class_name = parts[parts.index("class") + 1]
                return self.class_methods.get((fp, class_name), {}).get(method_name)
            return None

        base_symbol = call_name.split(".")[0]

        if fp in self.import_maps and base_symbol in self.import_maps[fp]:
            full_import_path = self.import_maps[fp][base_symbol]
            matched_id = self._find_matching_node_for_import(full_import_path, base_symbol)
            if matched_id:
                if "." in call_name:
                    remainder = call_name[len(base_symbol):]
                    return f"{matched_id}{remainder}"
                return matched_id
            
            return None

        if fp in self.module_defs and base_symbol in self.module_defs[fp]:
            target_id = self.module_defs[fp][base_symbol]
            if "." in call_name:
                remainder = call_name[len(base_symbol):]
                return f"{target_id}{remainder}"
            return target_id

        return None

    def _find_matching_node_for_import(self, full_import_path: str, symbol_name: str) -> Optional[str]:
        candidates = self.global_symbol_index.get(symbol_name, [])
        if not candidates:
            return None
        
        normalized_import = full_import_path.replace(".", os.sep)
        
        for cid in candidates:
            c_path = os.path.normpath(self.node_meta[cid]["file_path"])
            
            if normalized_import in c_path or os.path.splitext(os.path.basename(c_path))[0] in full_import_path:
                return cid
                
        return candidates[0] if len(candidates) == 1 else None