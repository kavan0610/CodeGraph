import numpy as np
from sentence_transformers import SentenceTransformer
from codegraph.database.sqlite import GraphStorage
from codegraph.build_graph.embedder import resolve_model_path, AVAILABLE_MODELS

class SemanticRetriever:
    _cached_model = None
    _cached_model_name = None

    def __init__(self, db_path: str = "codebase_graph.db", model_name: str = None):
        self.db_path = db_path
        self.storage = GraphStorage(db_path)

        if not model_name:
            stored_model = self.storage.get_metadata("embedding_model")
            model_name = stored_model if stored_model else "fast"

        self.canonical_name = AVAILABLE_MODELS.get(model_name.lower(), model_name)
        
        load_path = resolve_model_path(model_name)

        if SemanticRetriever._cached_model is None or SemanticRetriever._cached_model_name != self.canonical_name:
            print(f"Loading AI model for semantic search: {self.canonical_name}...")
            
            try:
                # Strict Offline Mode
                SemanticRetriever._cached_model = SentenceTransformer(load_path, local_files_only=True)
            except Exception:
                # Fallback to Download
                print(f"\nModel not found in local cache. Downloading {self.canonical_name}")
                SemanticRetriever._cached_model = SentenceTransformer(load_path, local_files_only=False)

            SemanticRetriever._cached_model_name = self.canonical_name

        self.model = SemanticRetriever._cached_model

    def search(self, query: str, top_k: int = 5) -> list:
        """Embeds the query and returns the most semantically similar nodes."""
        query_embedding = self.model.encode(query, show_progress_bar=False)

        nodes = self.storage.get_all_embeddings()
        if not nodes:
            print("No embeddings found")
            return []

        results = []
        for node in nodes:
            node_emb = np.frombuffer(node["embedding"], dtype=np.float32)

            norm_q = np.linalg.norm(query_embedding)
            norm_n = np.linalg.norm(node_emb)
            
            if norm_q == 0 or norm_n == 0:
                similarity = 0.0
            else:
                similarity = float(np.dot(query_embedding, node_emb) / (norm_q * norm_n))

            results.append((similarity, node))

        results.sort(key=lambda x: x[0], reverse=True)
        return results[:top_k]