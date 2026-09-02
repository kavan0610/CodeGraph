import ast
from typing import List, Tuple
from codegraph.dataclass.symbols import CodeNode, CodeEdge
import builtins

PYTHON_BUILTINS = set(dir(builtins))

PRIMITIVE_METHODS = {
    "append", "extend", "pop", "insert", "remove", "clear", "index", "count", 
    "sort", "reverse", "copy", "update", "get", "keys", "values", "items", 
    "setdefault", "split", "join", "replace", "strip", "format", "startswith", "endswith"
}

def is_noise_call(call_name: str) -> bool:
    """Determines if a call is a standard library/primitive function that should be ignored."""
    if not call_name:
        return True
        
    if call_name in PYTHON_BUILTINS:
        return True
        
    last_part = call_name.split(".")[-1]
    if last_part in PRIMITIVE_METHODS:
        return True
        
    if last_part.startswith("__") and last_part.endswith("__"):
        return True
        
    return False

class ComprehensiveASTVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str, source_code: str):
        self.file_path = file_path
        self.source_lines = source_code.splitlines()
        self.nodes: List[CodeNode] = []
        self.edges: List[CodeEdge] = []
        
        self.module_id = f"module:{file_path}"
        self.nodes.append(CodeNode(
            id=self.module_id, name=file_path, kind="module",
            file_path=file_path, start_line=1, end_line=len(self.source_lines),
            docstring=None, source_code=None
        ))
        
        self.context_stack = [self.module_id]

    @property
    def current_context(self):
        return self.context_stack[-1]

    def _get_source_segment(self, node: ast.AST) -> str:
        if not hasattr(node, 'lineno') or not hasattr(node, 'end_lineno'):
            return ""
        return "\n".join(self.source_lines[node.lineno - 1 : node.end_lineno])

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            target_id = f"ext:{alias.name}"
            self.edges.append(CodeEdge(self.current_context, target_id, "IMPORTS", node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            target_id = f"ext:{module}.{alias.name}"
            self.edges.append(CodeEdge(self.current_context, target_id, "IMPORTS", node.lineno))
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_id = f"class:{self.file_path}:{node.name}"
        
        self.nodes.append(CodeNode(
            id=class_id, name=node.name, kind="class", file_path=self.file_path,
            start_line=node.lineno, end_line=node.end_lineno,
            docstring=ast.get_docstring(node), source_code=self._get_source_segment(node)
        ))
        
        self.edges.append(CodeEdge(self.current_context, class_id, "DEFINES", node.lineno))

        for base in node.bases:
            base_name = self._get_call_name(base)
            if base_name:
                self.edges.append(CodeEdge(class_id, f"ext:{base_name}", "INHERITS", node.lineno))

        self.context_stack.append(class_id)
        self.generic_visit(node)
        self.context_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._handle_function(node, is_async=True)

    def _handle_function(self, node, is_async: bool):
        is_method = "class:" in self.current_context
        func_id = f"{'method' if is_method else 'func'}:{self.file_path}:{node.name}"
        
        self.nodes.append(CodeNode(
            id=func_id, name=node.name, kind="method" if is_method else "function",
            file_path=self.file_path, start_line=node.lineno, end_line=node.end_lineno,
            docstring=ast.get_docstring(node), source_code=self._get_source_segment(node)
        ))
        
        self.edges.append(CodeEdge(self.current_context, func_id, "DEFINES", node.lineno))

        self.context_stack.append(func_id)
        self.generic_visit(node)
        self.context_stack.pop()

    def visit_Call(self, node: ast.Call):
        target_name = self._get_call_name(node.func)
        
        if target_name and not is_noise_call(target_name):
            self.edges.append(CodeEdge(
                self.current_context, 
                f"call:{target_name}", 
                "CALLS", 
                node.lineno
            ))
        
        for arg in node.args:
            if isinstance(arg, (ast.Attribute, ast.Name)):
                callback_name = self._get_call_name(arg)
                if callback_name and not is_noise_call(callback_name):
                    self.edges.append(CodeEdge(
                        self.current_context, 
                        f"call:{callback_name}", 
                        "CALLS", 
                        node.lineno
                    ))
            self.visit(arg)
            
        for kwarg in node.keywords:
            if isinstance(kwarg.value, (ast.Attribute, ast.Name)):
                callback_name = self._get_call_name(kwarg.value)
                if callback_name and not is_noise_call(callback_name):
                    self.edges.append(CodeEdge(
                        self.current_context, 
                        f"call:{callback_name}", 
                        "CALLS", 
                        node.lineno
                    ))
            self.visit(kwarg.value)

    def _get_call_name(self, node: ast.AST) -> str:
        """Recursively resolves complex chained calls like `supabase.table().select().execute()`"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        elif isinstance(node, ast.Call):
            return self._get_call_name(node.func)
        return ""

    def visit_Assign(self, node: ast.Assign):
        if len(self.context_stack) == 1:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    var_id = f"var:{self.file_path}:{target.id}"
                    self.nodes.append(CodeNode(
                        id=var_id, name=target.id, kind="variable",
                        file_path=self.file_path, start_line=node.lineno, 
                        end_line=node.end_lineno, docstring=None, 
                        source_code=self._get_source_segment(node)
                    ))
                    self.edges.append(CodeEdge(self.current_context, var_id, "DEFINES", node.lineno))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if len(self.context_stack) == 1 and isinstance(node.target, ast.Name):
            var_id = f"var:{self.file_path}:{node.target.id}"
            self.nodes.append(CodeNode(
                id=var_id, name=node.target.id, kind="variable",
                file_path=self.file_path, start_line=node.lineno, 
                end_line=node.end_lineno, docstring=None, 
                source_code=self._get_source_segment(node)
            ))
            self.edges.append(CodeEdge(self.current_context, var_id, "DEFINES", node.lineno))
        self.generic_visit(node)

def parse_python_file(file_path: str) -> Tuple[List[CodeNode], List[CodeEdge]]:
    with open(file_path, "r", encoding="utf-8") as f:
        source_code = f.read()
    
    tree = ast.parse(source_code, filename=file_path)
    visitor = ComprehensiveASTVisitor(file_path, source_code)
    visitor.visit(tree)
    
    return visitor.nodes, visitor.edges