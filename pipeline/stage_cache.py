"""Idempotency helper (SPEC §11): a stage skips work when its output exists and the recorded
fingerprint of inputs, parameters and code matches. The fingerprint lives in ``<output>.meta.json``.

Code is part of the fingerprint (SPEC §13.38): params that name a ``stage`` (every stage) or a
``loader`` (prep) carry a digest of that module and every ``pipeline`` module it imports,
transitively, including the ``"pipeline.x:func"`` strings registries import lazily. The digest
is taken over the syntax tree without docstrings, so a comment or a reflowed line never
triggers a rebuild but a changed expression always does.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent
# bookkeeping modules whose edits cannot change any stage output (the fixture generator is
# left out too: its files are fingerprinted as inputs, so a regenerated world reruns anyway)
PLUMBING = frozenset({"pipeline.stage_cache", "pipeline.timing", "pipeline.__main__"})
_LAZY_REF = re.compile(r"^(pipeline(?:\.\w+)+):\w+$")


def _module_file(name: str, package_dir: Path) -> Path | None:
    parts = name.split(".")
    if parts[0] != package_dir.name:
        return None
    p = package_dir.joinpath(*parts[1:])
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    if p.with_suffix(".py").is_file():
        return p.with_suffix(".py")
    return None


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return tree


def _imports(name: str, path: Path, tree: ast.AST, root: str) -> set[str]:
    pkg = name if path.name == "__init__.py" else name.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names if a.name.split(".")[0] == root}
        elif isinstance(node, ast.ImportFrom):
            base = importlib.util.resolve_name("." * node.level + (node.module or ""), pkg) if node.level else (node.module or "")
            if base.split(".")[0] != root:
                continue
            parts = base.split(".")
            found |= {".".join(parts[: i + 1]) for i in range(len(parts))}  # parent packages run too
            found |= {f"{base}.{a.name}" for a in node.names}  # names that are not modules drop out below
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            m = _LAZY_REF.match(node.value)
            if m and root == "pipeline":
                found.add(m.group(1))
    return found


def module_closure(name: str, package_dir: Path = PACKAGE_DIR) -> dict[str, str]:
    """``{module: digest}`` for ``name`` and every package module it reaches."""
    root = package_dir.name
    seen: dict[str, str] = {}
    todo = [name]
    while todo:
        mod = todo.pop()
        if mod in seen or mod in PLUMBING or mod.startswith(f"{root}.fixtures"):
            continue
        path = _module_file(mod, package_dir)
        if path is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        todo += sorted(_imports(mod, path, tree, root))
        seen[mod] = hashlib.sha256(ast.dump(_strip_docstrings(tree)).encode()).hexdigest()[:16]
    return seen


@functools.cache
def code_version(name: str) -> str:
    """One digest for ``name`` and its transitive package imports (cached per process)."""
    closure = module_closure(name)
    if not closure:
        raise ValueError(f"no module {name!r} under {PACKAGE_DIR}")
    return hashlib.sha256(json.dumps(closure, sort_keys=True).encode()).hexdigest()[:16]


def _code(params: dict[str, Any]) -> str | None:
    if "loader" in params:
        return code_version(str(params["loader"]))
    if "stage" in params:
        return code_version(f"pipeline.stages.{params['stage']}")
    return None


def _file_fingerprint(path: Path) -> dict[str, Any]:
    st = path.stat()
    return {"path": str(path), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def fingerprint(inputs: list[Path], params: dict[str, Any]) -> str:
    payload = {
        "inputs": [_file_fingerprint(p) for p in inputs if p.exists()],
        "params": params,
        "code": _code(params),
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def meta_path(output: Path) -> Path:
    return output.with_suffix(output.suffix + ".meta.json")


def is_fresh(output: Path, inputs: list[Path], params: dict[str, Any], force: bool = False) -> bool:
    if force or not output.exists():
        return False
    recorded = read_meta(output)
    if not recorded:
        return False
    # an output replaced or truncated after it was recorded is not the one the meta describes
    if "output_bytes" in recorded and recorded["output_bytes"] != output.stat().st_size:
        return False
    return recorded.get("fingerprint") == fingerprint(inputs, params)


def write_atomic(path: Path, text: str) -> None:
    """Write via a sibling temp file and rename, so a crash never leaves half a file."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def record(output: Path, inputs: list[Path], params: dict[str, Any], extra: dict[str, Any] | None = None) -> None:
    payload = {"fingerprint": fingerprint(inputs, params), "params": params, "code": _code(params)}
    if output.is_file():
        payload["output_bytes"] = output.stat().st_size
    if extra:
        payload.update(extra)
    write_atomic(meta_path(output), json.dumps(payload, indent=2, sort_keys=True, default=str))


def read_meta(output: Path) -> dict[str, Any]:
    """The recorded sidecar (empty dict when missing or unreadable)."""
    mp = meta_path(output)
    if not mp.exists():
        return {}
    try:
        return json.loads(mp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
