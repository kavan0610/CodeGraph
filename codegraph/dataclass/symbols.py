from dataclasses import dataclass
from typing import Optional

@dataclass
class CodeNode:
    id: str
    name: str
    kind: str              # 'module', 'class', 'function', 'method'
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    docstring: Optional[str]
    source_code: Optional[str]

@dataclass
class CodeEdge:
    source_id: str
    target_id: str
    relation_type: str     # 'DEFINES', 'CALLS', 'IMPORTS', 'INHERITS'
    line_number: Optional[int] = None