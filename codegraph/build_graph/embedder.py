import os
import numpy as np
from typing import Dict
from sentence_transformers import SentenceTransformer
from codegraph.database.sqlite import GraphStorage

# Supported models and their default HuggingFace identifiers
AVAILABLE_MODELS = {
    "fast": "all-MiniLM-L6-v2",
    "quality": "BAAI/bge-small-en-v1.5",
    "strong": "BAAI/bge-base-en-v1.5"
}

def resolve_model_path(model_choice: str) -> str:
    """
    Resolves the model alias to its HuggingFace repository ID.
    The sentence-transformers library will automatically handle downloading
    and caching it to the system's local storage for offline support.
    """
    return AVAILABLE_MODELS.get(model_choice.lower(), model_choice)


class CodeEmbedder:
    def __init__(self, db_path: str = "codebase_graph.db", model_choice: str = "fast"):
        self.db_path = db_path
        self.storage = GraphStorage(db_path)

        self.canonical_model_name = AVAILABLE_MODELS.get(model_choice.lower(), model_choice)
        self.model_load_path = resolve_model_path(model_choice)

        self._check_model_switch()

        print(f"Loading AI Model '{self.canonical_model_name}'...")
        if os.path.isdir(self.model_load_path):
            print(f"Loaded locally from: {self.model_load_path}")
        
        try:
            self.model = SentenceTransformer(self.model_load_path, local_files_only=True)
        except Exception:
            print(f"Model not found in local cache. Downloading {self.model_load_path}")
            self.model = SentenceTransformer(self.model_load_path, local_files_only=False)

        self.storage.set_metadata("embedding_model", self.canonical_model_name)

    def _check_model_switch(self):
        """Detects if the user changed the embedding model on an existing DB."""
        previous_model = self.storage.get_metadata("embedding_model")
        if previous_model and previous_model != self.canonical_model_name:
            print(f"Model switch detected ({previous_model} -> {self.canonical_model_name}).")
            print("Resetting existing embeddings for full re-embedding...")
            self.storage.reset_all_embeddings()

    def _format_node_for_embedding(self, node: Dict) -> str:
        doc = node.get('docstring') or "No docstring provided."
        code = node.get('source_code') or ""
        return (
            f"Type: {node['kind'].capitalize()}\n"
            f"Name: {node['name']}\n"
            f"File: {node['file_path']}\n"
            f"Description: {doc}\n"
            f"Code:\n{code}"
        )

    def run(self, batch_size: int = 50):
        print("Checking database for unembedded nodes...")
        nodes = self.storage.get_unembedded_nodes()
        total = len(nodes)

        if total == 0:
            print("All nodes already have embeddings. Skipping AI model run.")
            return

        print(f"Generating vector embeddings for {total} new/modified nodes...")

        for i in range(0, total, batch_size):
            batch = nodes[i : i + batch_size]
            texts = [self._format_node_for_embedding(n) for n in batch]
            node_ids = [n['id'] for n in batch]

            embeddings_array = self.model.encode(texts, show_progress_bar=False)
            embeddings_bytes = [
                emb.astype(np.float32).tobytes() for emb in embeddings_array
            ]

            self.storage.update_embeddings(node_ids, embeddings_bytes)
            print(f"Processed {min(i + batch_size, total)} / {total} nodes...")

        print("All embeddings generated and saved to the database!")