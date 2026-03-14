from __future__ import annotations

import ast
import fnmatch
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .indexer import TEXT_EXTS, extract_symbols

try:
    from tree_sitter_languages import get_parser as ts_get_parser  # type: ignore
except Exception:  # pragma: no cover - optional runtime capability
    ts_get_parser = None


TS_LANGUAGE_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
}

TS_SYMBOL_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "method_definition",
    "class_definition",
    "class_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "variable_declarator",
    "lexical_declaration",
}

TS_COMPLEXITY_NODE_TYPES = {
    "if_statement",
    "else_clause",
    "for_statement",
    "while_statement",
    "switch_statement",
    "case_statement",
    "catch_clause",
    "conditional_expression",
}


def should_exclude(rel_path: str, excludes: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel_path, pattern) for pattern in excludes)


def iter_text_files(root: Path, excludes: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTS:
            continue
        rel = path.relative_to(root).as_posix()
        if should_exclude(rel, excludes):
            continue
        files.append(path)
    files.sort()
    return files


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    if b"\x00" in raw:
        return ""
    return raw.decode("utf-8-sig", errors="ignore")


def _resolve_file(root: Path, rel_path: str) -> Path:
    target = (root / rel_path).resolve()
    if not target.exists() or not target.is_file():
        raise ValueError(f"Path not found: {rel_path}")
    return target


def _ts_parser_for_suffix(suffix: str):
    if ts_get_parser is None:
        return None
    lang = TS_LANGUAGE_BY_EXT.get(suffix.lower())
    if not lang:
        return None
    try:
        return ts_get_parser(lang)
    except Exception:
        return None


def _ts_iter_nodes(root_node):
    stack = [root_node]
    while stack:
        node = stack.pop()
        yield node
        children = getattr(node, "children", [])
        if children:
            stack.extend(reversed(children))


def _ts_node_name(node, source_bytes: bytes) -> str | None:
    try:
        name_node = node.child_by_field_name("name")
    except Exception:
        name_node = None
    if name_node is not None:
        try:
            return source_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8", errors="ignore").strip()
        except Exception:
            return None
    return None


def _ts_node_snippet(node, text: str) -> str:
    lines = text.splitlines()
    start = int(node.start_point[0]) + 1
    end = int(node.end_point[0]) + 1
    if 1 <= start <= len(lines):
        return "\n".join(lines[start - 1 : min(end, len(lines))])
    return ""


def _ts_has_error(node) -> bool:
    for current in _ts_iter_nodes(node):
        if getattr(current, "type", "") == "ERROR":
            return True
        if getattr(current, "has_error", False):
            return True
    return False


def list_project_files(root: Path, excludes: list[str], limit: int = 200) -> dict[str, Any]:
    files = iter_text_files(root, excludes)
    rel_files = [path.relative_to(root).as_posix() for path in files[: max(1, limit)]]
    return {"root": str(root), "count": len(files), "files": rel_files}


def list_symbols(root: Path, rel_path: str, prefer_tree_sitter: bool = True) -> dict[str, Any]:
    target = _resolve_file(root, rel_path)
    suffix = target.suffix.lower()
    if suffix not in TEXT_EXTS:
        raise ValueError(f"Unsupported file type for symbol extraction: {target.suffix}")

    content = _read_text(target)
    if prefer_tree_sitter:
        parser = _ts_parser_for_suffix(suffix)
        if parser is not None and content:
            source_bytes = content.encode("utf-8")
            tree = parser.parse(source_bytes)
            items: list[dict[str, Any]] = []
            for node in _ts_iter_nodes(tree.root_node):
                if not getattr(node, "is_named", False):
                    continue
                if node.type not in TS_SYMBOL_NODE_TYPES:
                    continue
                items.append(
                    {
                        "name": _ts_node_name(node, source_bytes) or node.type,
                        "line_start": int(node.start_point[0]) + 1,
                        "line_end": int(node.end_point[0]) + 1,
                        "snippet": _ts_node_snippet(node, content)[:500],
                        "type": node.type,
                    }
                )
            return {"path": rel_path, "count": len(items), "symbols": items, "parser": "tree-sitter"}

    items = []
    for name, line_start, line_end, snippet in extract_symbols(target, content):
        items.append(
            {
                "name": name,
                "line_start": line_start,
                "line_end": line_end,
                "snippet": snippet[:500],
            }
        )
    return {"path": rel_path, "count": len(items), "symbols": items, "parser": "builtin"}


def query_python_ast(
    root: Path,
    rel_path: str,
    node_type: str | None = None,
    name_contains: str | None = None,
    prefer_tree_sitter: bool = True,
) -> dict[str, Any]:
    target = _resolve_file(root, rel_path)
    suffix = target.suffix.lower()
    content = _read_text(target)

    if suffix == ".py":
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise ValueError(f"Syntax error: {exc.msg} at line {exc.lineno}") from exc

        lines = content.splitlines()
        wanted = node_type.lower() if node_type else None
        name_filter = name_contains.lower() if name_contains else None
        matches: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            t_name = type(node).__name__
            if wanted and t_name.lower() != wanted:
                continue
            node_name = getattr(node, "name", None)
            if name_filter and (not isinstance(node_name, str) or name_filter not in node_name.lower()):
                continue
            lineno = getattr(node, "lineno", None)
            end_lineno = getattr(node, "end_lineno", lineno)
            snippet = ""
            if isinstance(lineno, int) and isinstance(end_lineno, int) and 1 <= lineno <= len(lines):
                snippet = "\n".join(lines[lineno - 1 : min(end_lineno, len(lines))])
            matches.append(
                {
                    "type": t_name,
                    "name": node_name,
                    "line_start": lineno,
                    "line_end": end_lineno,
                    "snippet": snippet[:500],
                }
            )
        return {"path": rel_path, "count": len(matches), "nodes": matches, "parser": "python-ast"}

    if not prefer_tree_sitter:
        raise ValueError("AST query for non-Python files requires tree-sitter support")

    parser = _ts_parser_for_suffix(suffix)
    if parser is None:
        raise ValueError("AST query for this file type requires optional tree-sitter parsers")
    if not content:
        return {"path": rel_path, "count": 0, "nodes": [], "parser": "tree-sitter"}

    source_bytes = content.encode("utf-8")
    tree = parser.parse(source_bytes)
    wanted = node_type.lower() if node_type else None
    name_filter = name_contains.lower() if name_contains else None
    matches: list[dict[str, Any]] = []
    for node in _ts_iter_nodes(tree.root_node):
        if not getattr(node, "is_named", False):
            continue
        t_name = node.type
        if wanted and t_name.lower() != wanted:
            continue
        node_name = _ts_node_name(node, source_bytes)
        if name_filter and (not node_name or name_filter not in node_name.lower()):
            continue
        matches.append(
            {
                "type": t_name,
                "name": node_name,
                "line_start": int(node.start_point[0]) + 1,
                "line_end": int(node.end_point[0]) + 1,
                "snippet": _ts_node_snippet(node, content)[:500],
            }
        )
    return {"path": rel_path, "count": len(matches), "nodes": matches, "parser": "tree-sitter"}


def validate_syntax(root: Path, rel_path: str, prefer_tree_sitter: bool = True) -> dict[str, Any]:
    target = _resolve_file(root, rel_path)
    content = _read_text(target)
    suffix = target.suffix.lower()

    if suffix == ".py":
        try:
            ast.parse(content)
            return {"path": rel_path, "valid": True, "language": "python", "parser": "python-ast"}
        except SyntaxError as exc:
            return {
                "path": rel_path,
                "valid": False,
                "language": "python",
                "parser": "python-ast",
                "error": f"{exc.msg} at line {exc.lineno}",
            }

    if prefer_tree_sitter:
        parser = _ts_parser_for_suffix(suffix)
        if parser is not None:
            tree = parser.parse(content.encode("utf-8"))
            if _ts_has_error(tree.root_node):
                return {
                    "path": rel_path,
                    "valid": False,
                    "language": suffix.lstrip("."),
                    "parser": "tree-sitter",
                    "error": "Syntax error detected by tree-sitter",
                }
            return {"path": rel_path, "valid": True, "language": suffix.lstrip("."), "parser": "tree-sitter"}

    bracket_pairs = {"(": ")", "[": "]", "{": "}"}
    openers = set(bracket_pairs)
    closers = {v: k for k, v in bracket_pairs.items()}
    stack: list[str] = []
    for ch in content:
        if ch in openers:
            stack.append(ch)
        elif ch in closers:
            if not stack or stack[-1] != closers[ch]:
                return {
                    "path": rel_path,
                    "valid": False,
                    "language": suffix.lstrip("."),
                    "parser": "bracket-check",
                    "error": "Unbalanced brackets",
                }
            stack.pop()
    valid = not stack
    payload: dict[str, Any] = {
        "path": rel_path,
        "valid": valid,
        "language": suffix.lstrip("."),
        "parser": "bracket-check",
    }
    if not valid:
        payload["error"] = "Unbalanced brackets"
    return payload


def _python_dependencies(content: str) -> list[str]:
    deps: set[str] = set()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                deps.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            deps.add(node.module)
    return sorted(deps)


JS_IMPORT_RE = re.compile(r"""^\s*import\s+(?:.+?\s+from\s+)?["']([^"']+)["']""")
JS_REQUIRE_RE = re.compile(r"""require\(\s*["']([^"']+)["']\s*\)""")


def _js_dependencies(content: str) -> list[str]:
    deps: set[str] = set()
    for line in content.splitlines():
        m = JS_IMPORT_RE.match(line)
        if m:
            deps.add(m.group(1))
    for m in JS_REQUIRE_RE.finditer(content):
        deps.add(m.group(1))
    return sorted(deps)


def analyze_dependencies(root: Path, rel_path: str) -> dict[str, Any]:
    target = _resolve_file(root, rel_path)
    content = _read_text(target)
    suffix = target.suffix.lower()
    if suffix == ".py":
        deps = _python_dependencies(content)
    elif suffix in {".js", ".jsx", ".ts", ".tsx"}:
        deps = _js_dependencies(content)
    else:
        deps = []
    return {"path": rel_path, "count": len(deps), "dependencies": deps}


def _python_function_complexity(node: ast.AST) -> int:
    score = 1
    branch_nodes = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.BoolOp,
        ast.IfExp,
        ast.comprehension,
        ast.Match,
    )
    for child in ast.walk(node):
        if isinstance(child, branch_nodes):
            score += 1
    return score


def analyze_complexity(root: Path, rel_path: str, prefer_tree_sitter: bool = True) -> dict[str, Any]:
    target = _resolve_file(root, rel_path)
    content = _read_text(target)
    suffix = target.suffix.lower()
    lines = content.splitlines()

    if suffix == ".py":
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise ValueError(f"Syntax error: {exc.msg} at line {exc.lineno}") from exc
        functions: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end_lineno = getattr(node, "end_lineno", node.lineno)
                functions.append(
                    {
                        "name": node.name,
                        "line_start": node.lineno,
                        "line_end": end_lineno,
                        "lines": max(1, int(end_lineno) - int(node.lineno) + 1),
                        "cyclomatic": _python_function_complexity(node),
                    }
                )
        total_complexity = sum(item["cyclomatic"] for item in functions)
        return {
            "path": rel_path,
            "language": "python",
            "line_count": len(lines),
            "function_count": len(functions),
            "total_cyclomatic": total_complexity,
            "functions": sorted(functions, key=lambda item: item["cyclomatic"], reverse=True),
            "parser": "python-ast",
        }

    if prefer_tree_sitter:
        parser = _ts_parser_for_suffix(suffix)
        if parser is not None and content:
            tree = parser.parse(content.encode("utf-8"))
            branch_count = sum(1 for node in _ts_iter_nodes(tree.root_node) if node.type in TS_COMPLEXITY_NODE_TYPES)
            return {
                "path": rel_path,
                "language": suffix.lstrip("."),
                "line_count": len(lines),
                "estimated_complexity": max(1, branch_count + 1),
                "parser": "tree-sitter",
            }

    branch_tokens = len(re.findall(r"\b(if|for|while|case|catch|\&\&|\|\|)\b", content))
    return {
        "path": rel_path,
        "language": suffix.lstrip("."),
        "line_count": len(lines),
        "estimated_complexity": max(1, branch_tokens + 1),
        "parser": "token-estimate",
    }


def find_symbol_usage(root: Path, excludes: list[str], symbol: str, limit: int = 50) -> dict[str, Any]:
    if not symbol or not symbol.strip():
        raise ValueError("symbol is required")
    pattern = re.compile(rf"\b{re.escape(symbol)}\b")
    hits: list[dict[str, Any]] = []
    for path in iter_text_files(root, excludes):
        rel = path.relative_to(root).as_posix()
        content = _read_text(path)
        if not content:
            continue
        for lineno, line in enumerate(content.splitlines(), start=1):
            if not pattern.search(line):
                continue
            hits.append({"path": rel, "line": lineno, "snippet": line.strip()[:300]})
            if len(hits) >= max(1, limit):
                return {"symbol": symbol, "count": len(hits), "results": hits}
    return {"symbol": symbol, "count": len(hits), "results": hits}


def project_stats(root: Path, excludes: list[str]) -> dict[str, Any]:
    files = iter_text_files(root, excludes)
    ext_counts: Counter[str] = Counter()
    total_lines = 0
    total_symbols = 0
    for path in files:
        ext_counts[path.suffix.lower() or "<none>"] += 1
        content = _read_text(path)
        total_lines += len(content.splitlines())
        total_symbols += len(extract_symbols(path, content))
    by_language = [
        {"extension": key, "files": value}
        for key, value in sorted(ext_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "root": str(root),
        "files": len(files),
        "lines": total_lines,
        "symbols": total_symbols,
        "languages": by_language,
    }
