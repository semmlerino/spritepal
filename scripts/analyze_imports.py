#!/usr/bin/env python3
from __future__ import annotations

"""
Analyze import patterns and dependencies in the SpritePal codebase.
Identifies:
- Circular imports
- Conditional imports (inside functions/try blocks)
- Module dependency graph
- Import location violations
"""

import ast
import json
from collections import defaultdict
from pathlib import Path


class ImportAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze import patterns."""

    def __init__(self, filename: str):
        self.filename = filename
        self.module_name = self._path_to_module(filename)
        self.imports: list[dict] = []
        self.conditional_imports: list[dict] = []
        self.function_stack: list[str] = []
        self.in_try_block = False
        self.in_except_block = False
        self.current_line = 0

    def _path_to_module(self, path: str) -> str:
        """Convert file path to module name."""
        # Remove project root and convert to module
        parts = Path(path).parts
        if "spritepal" in parts:
            idx = parts.index("spritepal")
            parts = parts[idx:]

        # Remove .py extension and join with dots
        module_parts = list(parts)
        module_parts[-1] = module_parts[-1].removesuffix(".py")

        return ".".join(module_parts)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Track when we're inside a function."""
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Track when we're inside an async function."""
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Try(self, node: ast.Try):
        """Track when we're inside a try block."""
        old_try = self.in_try_block
        self.in_try_block = True

        # Visit try body
        for stmt in node.body:
            self.visit(stmt)

        # Visit except handlers
        old_except = self.in_except_block
        self.in_except_block = True
        for handler in node.handlers:
            self.visit(handler)
        self.in_except_block = old_except

        self.in_try_block = old_try

        # Visit else and finally
        for stmt in node.orelse + node.finalbody:
            self.visit(stmt)

    def visit_Import(self, node: ast.Import):
        """Record import statements."""
        for alias in node.names:
            import_info = {
                "type": "import",
                "module": alias.name,
                "alias": alias.asname,
                "line": node.lineno,
                "in_function": bool(self.function_stack),
                "function": self.function_stack[-1] if self.function_stack else None,
                "in_try": self.in_try_block,
                "in_except": self.in_except_block,
            }

            if import_info["in_function"] or import_info["in_try"]:
                self.conditional_imports.append(import_info)
            else:
                self.imports.append(import_info)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Record from...import statements."""
        module = node.module or ""
        level = node.level  # Number of dots for relative imports

        # Handle relative imports
        if level > 0:
            module = "." * level + module

        for alias in node.names:
            import_info = {
                "type": "from",
                "module": module,
                "name": alias.name,
                "alias": alias.asname,
                "line": node.lineno,
                "in_function": bool(self.function_stack),
                "function": self.function_stack[-1] if self.function_stack else None,
                "in_try": self.in_try_block,
                "in_except": self.in_except_block,
            }

            if import_info["in_function"] or import_info["in_try"]:
                self.conditional_imports.append(import_info)
            else:
                self.imports.append(import_info)


def analyze_file(filepath: Path) -> tuple[list[dict], list[dict]]:
    """Analyze a single Python file for imports."""
    try:
        with filepath.open(encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content, filename=str(filepath))
        analyzer = ImportAnalyzer(str(filepath))
        analyzer.visit(tree)

        return analyzer.imports, analyzer.conditional_imports
    except Exception as e:
        print(f"Error analyzing {filepath}: {e}")
        return [], []


def build_dependency_graph(project_root: Path) -> dict[str, set[str]]:
    """Build a dependency graph for the entire project."""
    dependencies = defaultdict(set)
    conditional_imports_by_file = {}

    # Analyze all Python files
    for py_file in project_root.rglob("*.py"):
        # Skip test files and scripts
        if any(skip in str(py_file) for skip in ["test_", "__pycache__", ".venv", "venv", "scripts/"]):
            continue

        imports, conditional = analyze_file(py_file)
        module_name = str(py_file.relative_to(project_root)).replace("/", ".").replace(".py", "")

        # Record regular imports
        for imp in imports:
            if imp["module"].startswith("spritepal"):
                dependencies[module_name].add(imp["module"])

        # Record conditional imports
        if conditional:
            conditional_imports_by_file[module_name] = conditional

    return dict(dependencies), conditional_imports_by_file


def find_circular_imports(dependencies: dict[str, set[str]]) -> list[list[str]]:
    """Find circular import chains."""

    def find_cycle(node: str, path: list[str], visited: set[str]) -> list[str] | None:
        if node in path:
            # Found a cycle
            cycle_start = path.index(node)
            return [*path[cycle_start:], node]

        if node in visited:
            return None

        visited.add(node)
        path.append(node)

        for dep in dependencies.get(node, []):
            cycle = find_cycle(dep, path.copy(), visited.copy())
            if cycle:
                return cycle

        return None

    cycles = []
    all_modules = set(dependencies.keys())

    for module in all_modules:
        cycle = find_cycle(module, [], set())
        if cycle and cycle not in cycles:
            cycles.append(cycle)

    return cycles


def main():
    """Main analysis function."""
    project_root = Path(__file__).parent.parent

    print("Analyzing imports in SpritePal...")
    print("=" * 60)

    # Build dependency graph
    dependencies, conditional_imports = build_dependency_graph(project_root)

    # Find circular imports
    cycles = find_circular_imports(dependencies)

    # Report findings
    print("\n📊 Import Analysis Summary:")
    print(f"Total modules analyzed: {len(dependencies)}")
    print(f"Modules with conditional imports: {len(conditional_imports)}")
    print(f"Circular import chains found: {len(cycles)}")

    # Show conditional imports
    if conditional_imports:
        print("\n⚠️  Conditional Imports (may indicate problems):")
        for module, imports in sorted(conditional_imports.items()):
            print(f"\n{module}:")
            for imp in imports:
                location = f"line {imp['line']}"
                if imp["in_function"]:
                    location += f" in {imp['function']}()"
                elif imp["in_try"]:
                    location += " in try block"
                print(f"  - {imp['module']} ({location})")

    # Show circular imports
    if cycles:
        print("\n🔄 Circular Import Chains:")
        for i, cycle in enumerate(cycles, 1):
            print(f"\n{i}. " + " → ".join(cycle))

    # Show modules with most dependencies
    print("\n📦 Modules with most dependencies:")
    sorted_deps = sorted(dependencies.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    for module, deps in sorted_deps:
        print(f"  {module}: {len(deps)} dependencies")

    # Check for layer violations
    print("\n🚫 Potential Layer Violations:")
    for module, deps in dependencies.items():
        # Check if core imports from UI
        if module.startswith(("core.", "utils.")):
            ui_deps = [d for d in deps if d.startswith("ui.")]
            if ui_deps:
                print(f"  {module} imports from UI layer: {', '.join(ui_deps)}")

    # Save detailed report
    report_path = project_root / "import_analysis_report.json"
    with report_path.open("w") as f:
        json.dump(
            {
                "dependencies": {k: list(v) for k, v in dependencies.items()},
                "conditional_imports": conditional_imports,
                "circular_imports": cycles,
            },
            f,
            indent=2,
        )
    print(f"\n✅ Detailed report saved to: {report_path}")


if __name__ == "__main__":
    main()
