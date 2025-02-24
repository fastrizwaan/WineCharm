import ast
import sys
from collections import defaultdict

class ParentTransformer(ast.NodeTransformer):
    def visit(self, node):
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        item.parent = node
                        self.visit(item)
            elif isinstance(value, ast.AST):
                value.parent = node
                self.visit(value)
        return node

class ClassVisitor(ast.NodeVisitor):
    def __init__(self):
        self.classes = {}

    def visit_ClassDef(self, node):
        methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
        self.classes[node.name] = methods
        self.generic_visit(node)

class FunctionVisitor(ast.NodeVisitor):
    def __init__(self):
        self.functions = []

    def visit_FunctionDef(self, node):
        if not any(isinstance(parent, ast.ClassDef) for parent in self._get_parents(node)):
            self.functions.append(node.name)
        self.generic_visit(node)

    def _get_parents(self, node):
        parents = []
        while hasattr(node, 'parent'):
            node = node.parent
            parents.append(node)
        return parents

class InstanceVisitor(ast.NodeVisitor):
    def __init__(self, class_names):
        self.class_names = class_names
        self.instances = defaultdict(list)

    def visit_Assign(self, node):
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id in self.class_names:
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.instances[node.value.func.id].append(target.id)
        self.generic_visit(node)

class MethodReferenceVisitor(ast.NodeVisitor):
    def __init__(self, classes, standalone_functions):
        self.classes = classes
        self.standalone_functions = standalone_functions
        self.used_methods = set()
        self.used_functions = set()
        self.current_class = None

    def visit_ClassDef(self, node):
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = None

    def visit_Attribute(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == 'self' and self.current_class:
            if node.attr in self.classes.get(self.current_class, []):
                self.used_methods.add((self.current_class, node.attr))
        self.generic_visit(node)

    def visit_Call(self, node):
        # Check direct method calls
        if isinstance(node.func, ast.Attribute):
            self._check_method_call(node.func)
        
        # Check signal connections: obj.connect("signal", self.method)
        if (isinstance(node.func, ast.Attribute) and 
            node.func.attr == 'connect' and 
            len(node.args) >= 2 and 
            isinstance(node.args[1], ast.Attribute)):
            self._check_method_call(node.args[1])

        # Check all arguments for method references
        for arg in node.args:
            if isinstance(arg, ast.Attribute):
                self._check_method_call(arg)
            elif isinstance(arg, (ast.List, ast.Tuple)):
                for elt in arg.elts:
                    if isinstance(elt, ast.Attribute):
                        self._check_method_call(elt)

        self.generic_visit(node)

    def _check_method_call(self, node):
        if isinstance(node.value, ast.Name) and node.value.id == 'self' and self.current_class:
            if node.attr in self.classes.get(self.current_class, []):
                self.used_methods.add((self.current_class, node.attr))

def find_unused_methods_and_functions(file_path):
    with open(file_path) as f:
        code = f.read()

    tree = ast.parse(code)
    ParentTransformer().visit(tree)
    ast.fix_missing_locations(tree)

    # Collect class methods and standalone functions
    class_visitor = ClassVisitor()
    class_visitor.visit(tree)
    classes = class_visitor.classes

    function_visitor = FunctionVisitor()
    function_visitor.visit(tree)
    standalone_functions = function_visitor.functions

    # Track method references
    reference_visitor = MethodReferenceVisitor(classes, standalone_functions)
    reference_visitor.visit(tree)

    # Calculate unused items
    all_methods = {(c, m) for c, ms in classes.items() for m in ms}
    unused_methods = [
        f"{c}.{m}" for c, m in (all_methods - reference_visitor.used_methods)
    ]
    unused_functions = [
        f for f in standalone_functions if f not in reference_visitor.used_functions
    ]

    return sorted(unused_methods), sorted(unused_functions)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 winecharm_analyzer.py winecharm.py")
        sys.exit(1)

    unused_methods, unused_functions = find_unused_methods_and_functions(sys.argv[1])

    if unused_methods:
        print("Potentially unused methods:")
        for m in unused_methods:
            print(f"  - {m}")

    if unused_functions:
        print("\nPotentially unused functions:")
        for f in unused_functions:
            print(f"  - {f}")
