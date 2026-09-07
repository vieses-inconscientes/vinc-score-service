from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN_CORE_IMPORTS = frozenset({"fastapi", "openai"})


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_core_has_no_direct_fastapi_or_openai_imports() -> None:
    root = Path(__file__).parents[1] / "src" / "vinc_agent"
    violations = {
        path.name: sorted(_import_roots(path) & FORBIDDEN_CORE_IMPORTS)
        for path in root.glob("*.py")
        if _import_roots(path) & FORBIDDEN_CORE_IMPORTS
    }
    assert violations == {}
