"""AST scanner — the core engine of codegraph.

Parses every .py file in a project using Python's ast module to extract:
- Classes with bases, methods, signatures, and docstrings
- Top-level functions with signatures and type annotations
- Import statements mapped to actual file paths
- Git history per file (commit SHA, author, date, message)
- Transitive impact analysis (if file X changes, what else breaks)

The main entry point is scan_project() which returns a complete graph dict.
No external dependencies — uses only Python stdlib.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path


# Module color palette (auto-assigned to discovered modules)
_PALETTE = [
    "#4A90D9", "#E67E22", "#9B59B6", "#2ECC71", "#E74C3C",
    "#1ABC9C", "#F39C12", "#3498DB", "#8E44AD", "#D35400",
    "#7F8C8D", "#C0392B", "#95A5A6", "#16A085", "#2980B9",
    "#D4AC0D", "#AF7AC5", "#48C9B0", "#F1948A", "#85C1E9",
]


def _get_module_name(filepath: Path, root: Path) -> str:
    rel = filepath.relative_to(root)
    parts = rel.parts
    return parts[0] if len(parts) > 1 else "root"


def _get_signature(node: ast.AST) -> str:
    args = []
    for arg in node.args.args:
        ann = ": " + ast.unparse(arg.annotation) if arg.annotation else ""
        args.append(arg.arg + ann)
    ret = " -> " + ast.unparse(node.returns) if node.returns else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(args)}){ret}"


def _get_docstring(node: ast.AST) -> str:
    ds = ast.get_docstring(node)
    if ds:
        return ds.strip().split("\n")[0]
    return ""


def parse_file(filepath: Path) -> dict:
    """Parse a Python file and extract structure, signatures, and source."""
    try:
        source = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return {"classes": [], "functions": [], "imports": [], "source": ""}

    try:
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return {"classes": [], "functions": [], "imports": [], "source": source}

    classes, functions, imports = [], [], []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = []
            for n in node.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({
                        "name": n.name,
                        "signature": _get_signature(n),
                        "line": n.lineno,
                    })
            classes.append({
                "name": node.name,
                "methods": methods,
                "line": node.lineno,
                "docstring": _get_docstring(node),
                "bases": [ast.unparse(b) for b in node.bases],
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if hasattr(node, "col_offset") and node.col_offset == 0:
                functions.append({
                    "name": node.name,
                    "signature": _get_signature(node),
                    "line": node.lineno,
                    "async": isinstance(node, ast.AsyncFunctionDef),
                    "docstring": _get_docstring(node),
                })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return {"classes": classes, "functions": functions, "imports": imports, "source": source}


def resolve_import(import_path: str, all_files: dict[str, str]) -> str | None:
    """Try to resolve an import string to a project file path."""
    candidates = [
        import_path.replace(".", "/") + ".py",
        import_path.replace(".", "/") + "/__init__.py",
    ]
    # Try common prefixes
    for prefix in ("", "src/", "lib/", "app/"):
        stripped = import_path
        if import_path.startswith(prefix.rstrip("/")):
            stripped = import_path[len(prefix.rstrip("/")) + 1:] if prefix else import_path
        candidates.extend([
            prefix + stripped.replace(".", "/") + ".py",
            prefix + stripped.replace(".", "/") + "/__init__.py",
        ])

    for candidate in candidates:
        if candidate in all_files:
            return candidate
    return None


def compute_hash(filepath: Path) -> str:
    content = filepath.read_bytes()
    return hashlib.sha256(content).hexdigest()[:12].upper()


def get_git_history(filepath: Path, project_root: Path, max_commits: int = 10) -> list[dict]:
    rel_path = str(filepath.relative_to(project_root)).replace("\\", "/")
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={max_commits}",
             "--format=%H|%an|%ae|%aI|%s", "--", rel_path],
            capture_output=True, text=True, cwd=str(project_root), timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return []
        commits = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 4)
            if len(parts) == 5:
                commits.append({
                    "sha": parts[0][:8],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "message": parts[4],
                })
        return commits
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def get_all_authors(project_root: Path) -> dict[str, list[str]]:
    try:
        result = subprocess.run(
            ["git", "log", "--format=%an|%H", "--name-only"],
            capture_output=True, text=True, cwd=str(project_root), timeout=30,
            check=False,
        )
        if result.returncode != 0:
            return {}
        authors: dict[str, set[str]] = {}
        current_author = None
        for line in result.stdout.splitlines():
            if "|" in line:
                current_author = line.split("|")[0]
                if current_author not in authors:
                    authors[current_author] = set()
            elif line.strip() and current_author:
                authors[current_author].add(line.strip())
        return {a: sorted(files) for a, files in authors.items()}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {}


def compute_impact(nodes: list[dict], edges: list[dict]) -> dict[str, list[str]]:
    """BFS downstream impact for each file."""
    reverse_deps: dict[str, set[str]] = {n["id"]: set() for n in nodes}
    for edge in edges:
        if edge["target"] in reverse_deps:
            reverse_deps[edge["target"]].add(edge["source"])

    impact: dict[str, list[str]] = {}
    for node in nodes:
        visited = set()
        queue = [node["id"]]
        while queue:
            current = queue.pop(0)
            for dependent in reverse_deps.get(current, set()):
                if dependent not in visited and dependent != node["id"]:
                    visited.add(dependent)
                    queue.append(dependent)
        impact[node["id"]] = sorted(visited)
    return impact


def scan_project(project_root: Path, directories: list[str] | None = None) -> dict:
    """Scan a project directory and build the full dependency graph.

    Args:
        project_root: Root directory of the project.
        directories: Subdirectories to scan. If None, auto-detects Python packages.

    Returns:
        Full graph data dict with nodes, edges, impact, stats, colors, etc.
    """
    project_root = project_root.resolve()

    # Auto-detect directories if not specified
    if directories is None:
        directories = []
        for item in sorted(project_root.iterdir()):
            if item.is_dir() and not item.name.startswith(".") and not item.name.startswith("_"):
                # Check if it contains .py files
                if any(item.rglob("*.py")):
                    directories.append(item.name)
        # Also check root-level .py files
        if any(project_root.glob("*.py")):
            directories.append(".")

    all_nodes = []
    for dir_name in directories:
        dir_path = project_root / dir_name if dir_name != "." else project_root
        if not dir_path.exists():
            continue

        py_files = sorted(dir_path.rglob("*.py")) if dir_name != "." else sorted(
            project_root.glob("*.py"))

        for filepath in py_files:
            rel_path = str(filepath.relative_to(project_root)).replace("\\", "/")
            try:
                stat = filepath.stat()
                source = filepath.read_text(encoding="utf-8", errors="replace")
            except (PermissionError, OSError):
                continue

            line_count = len(source.splitlines())
            if line_count == 0:
                continue

            module = _get_module_name(filepath, dir_path) if dir_name != "." else "root"
            if dir_name in ("tests", "test"):
                module = "tests"

            parsed = parse_file(filepath)
            file_hash = compute_hash(filepath)
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

            all_nodes.append({
                "id": rel_path,
                "label": filepath.name,
                "module": module,
                "path": rel_path,
                "lines": line_count,
                "hash": file_hash,
                "modified": modified,
                "size_bytes": stat.st_size,
                "classes": parsed["classes"],
                "functions": parsed["functions"],
                "source": parsed["source"],
                "raw_imports": parsed["imports"],
                "git_history": get_git_history(filepath, project_root),
            })

    # Build edges
    all_files = {node["id"]: node for node in all_nodes}
    edges = []
    edge_set = set()
    for node in all_nodes:
        for imp in node["raw_imports"]:
            target = resolve_import(imp, all_files)
            if target and target != node["id"]:
                edge_key = f"{node['id']}→{target}"
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    edges.append({"source": node["id"], "target": target, "import": imp})

    for node in all_nodes:
        del node["raw_imports"]

    # Compute impact
    edge_ids = [{"source": e["source"], "target": e["target"]} for e in edges]
    impact = compute_impact(all_nodes, edge_ids)

    # Assign colors to modules
    modules = sorted(set(n["module"] for n in all_nodes))
    colors = {mod: _PALETTE[i % len(_PALETTE)] for i, mod in enumerate(modules)}

    # Git authors
    authors = get_all_authors(project_root)

    # Stats
    stats = {
        "total_files": len(all_nodes),
        "total_lines": sum(n["lines"] for n in all_nodes),
        "total_edges": len(edges),
        "modules": {},
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "project_root": str(project_root),
    }
    for node in all_nodes:
        mod = node["module"]
        if mod not in stats["modules"]:
            stats["modules"][mod] = {"files": 0, "lines": 0}
        stats["modules"][mod]["files"] += 1
        stats["modules"][mod]["lines"] += node["lines"]

    return {
        "nodes": all_nodes,
        "edges": edges,
        "impact": impact,
        "roles": {"roles": {}, "assignments": {}},
        "authors": authors,
        "stats": stats,
        "colors": colors,
    }


def build_file_index(graph: dict) -> dict:
    """Build token-efficient file index for agent consumption."""
    index = {
        "version": 1,
        "generated_at": graph["stats"]["generated_at"],
        "stats": graph["stats"],
        "files": {},
    }

    for node in graph["nodes"]:
        file_id = node["id"]
        class_summaries = []
        for cls in node["classes"]:
            class_summaries.append({
                "name": cls["name"],
                "bases": cls.get("bases", []),
                "docstring": cls.get("docstring", ""),
                "methods": [
                    m["signature"] if isinstance(m, dict) else m
                    for m in cls["methods"]
                ],
            })

        func_summaries = []
        for fn in node["functions"]:
            func_summaries.append({
                "signature": fn.get("signature", fn["name"]),
                "docstring": fn.get("docstring", ""),
            })

        deps_in = [e["target"] for e in graph["edges"] if e["source"] == file_id]
        deps_out = [e["source"] for e in graph["edges"] if e["target"] == file_id]

        index["files"][file_id] = {
            "module": node["module"],
            "lines": node["lines"],
            "hash": node["hash"],
            "classes": class_summaries,
            "functions": func_summaries,
            "imports_from": deps_in,
            "imported_by": deps_out,
            "impact_radius": len(graph["impact"].get(file_id, [])),
            "last_commit": (
                node["git_history"][0] if node.get("git_history") else None
            ),
        }

    return index
