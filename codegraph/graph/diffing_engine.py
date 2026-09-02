import os
from typing import Tuple, List, Dict, Set

try:
    import pathspec
except ImportError:
    pathspec = None


class DiffingEngine:
    def __init__(self, storage):
        self.storage = storage

    def _load_gitignore(self, root_dir: str):
        """
        Loads and compiles .gitignore rules from root_dir.
        Returns a PathSpec object if found, otherwise None.
        """
        gitignore_path = os.path.join(root_dir, ".gitignore")
        if os.path.isfile(gitignore_path) and pathspec is not None:
            with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            
            lines.append(".git/\n")
            return pathspec.PathSpec.from_lines("gitwildmatch", lines)
        return None

    def get_changed_files(self, root_dir: str, default_ignore_dirs: Set[str]) -> Tuple[List[str], List[str], Dict[str, float]]:
        """
        Scans disk, compares against DB, and returns (to_parse, to_delete, disk_state).
        Uses .gitignore if present; falls back to default_ignore_dirs if absent.
        """
        spec = self._load_gitignore(root_dir)
        if spec:
            print("Found .gitignore — filtering files using gitignore rules.")
        else:
            print("No .gitignore found — falling back to default ignore list.")

        db_state = self.storage.get_all_mtimes()
        disk_state = {}

        for root, dirs, files in os.walk(root_dir):
            rel_root = os.path.relpath(root, root_dir)

            if spec:
                valid_dirs = []
                for d in dirs:
                    rel_dir = os.path.normpath(os.path.join(rel_root, d)).replace("\\", "/")
                    if rel_dir == ".":
                        valid_dirs.append(d)
                        continue
                    if not (spec.match_file(rel_dir) or spec.match_file(rel_dir + "/")):
                        valid_dirs.append(d)
                dirs[:] = valid_dirs
            else:
                dirs[:] = [d for d in dirs if d not in default_ignore_dirs]

            for file in files:
                if not file.endswith(".py"):
                    continue

                rel_file = os.path.normpath(os.path.join(rel_root, file)).replace("\\", "/")

                if spec and spec.match_file(rel_file):
                    continue

                abs_path = os.path.abspath(os.path.join(root, file))
                disk_state[abs_path] = os.path.getmtime(abs_path)

        to_parse = []
        to_delete = []

        for path, mtime in disk_state.items():
            if path not in db_state:
                to_parse.append(path)
            elif db_state[path] < mtime:
                to_parse.append(path)
                to_delete.append(path)

        for path in db_state:
            if path not in disk_state:
                to_delete.append(path)

        return to_parse, to_delete, disk_state