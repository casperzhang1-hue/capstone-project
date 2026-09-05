"""Enforce concise English API documentation."""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    *sorted((PROJECT_ROOT / "src" / "openet2").glob("*.py")),
    PROJECT_ROOT / "docker" / "legacy_code" / "create_data_folder.py",
    PROJECT_ROOT / "references" / "client_delay_comparison" / "rebuild_figures.py",
    PROJECT_ROOT / "reports" / "client_data" / "client_delay_evidence" / "rebuild_figures.py",
)


def _all_python_files() -> tuple[Path, ...]:
    return tuple(sorted(PROJECT_ROOT.rglob("*.py")))


def test_every_class_has_a_docstring() -> None:
    missing: list[str] = []
    for path in _all_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not ast.get_docstring(node):
                missing.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {node.name}")
    assert not missing, "Classes without docstrings:\n" + "\n".join(missing)


def test_public_runtime_functions_have_docstrings() -> None:
    missing: list[str] = []
    for path in RUNTIME_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            public = not node.name.startswith("_") or node.name in {"__init__", "__post_init__"}
            if public and not ast.get_docstring(node):
                missing.append(f"{path.relative_to(PROJECT_ROOT)}:{node.lineno} {node.name}")
    assert not missing, "Public functions without docstrings:\n" + "\n".join(missing)


def test_comments_and_docstrings_are_concise_english() -> None:
    invalid: list[str] = []
    for path in _all_python_files():
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(PROJECT_ROOT)
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT and not token.string.isascii():
                invalid.append(f"{relative}:{token.start[0]} non-English comment")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = ast.get_docstring(node, clean=True)
            if not docstring:
                continue
            line = getattr(node, "lineno", 1)
            if not docstring.isascii():
                invalid.append(f"{relative}:{line} non-English docstring")
            if "\n" in docstring or len(docstring) > 100:
                invalid.append(f"{relative}:{line} long docstring")
    assert not invalid, "Documentation quality issues:\n" + "\n".join(invalid)
