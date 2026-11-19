"""Pro Datei: Komplexität (lizard) und Syntax-Extraktion (tree-sitter). Läuft parallel."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import lizard
from tree_sitter import Parser

from .inventory import DEP_FAMILY, SourceFile
from .langs import java, python, typescript
from .langs.base import Parsed

_GRAMMAR = {"typescript": "typescript", "tsx": "tsx", "javascript": "javascript", "java": "java", "python": "python"}
_EXTRACT = {"ts": typescript.extract, "java": java.extract, "python": python.extract}


@dataclass
class FileResult:
    path: str
    nloc: int = 0
    lines: int = 0
    functions: list[dict] = field(default_factory=list)
    parsed: Parsed | None = None
    error: str | None = None


@lru_cache(maxsize=None)
def _parser(grammar: str) -> Parser:
    from tree_sitter_language_pack import get_parser

    return get_parser(grammar)


def analyze_file(root: str, path: str, lang: str) -> FileResult:
    result = FileResult(path)
    try:
        raw = (Path(root) / path).read_bytes()
        code = raw.decode("utf-8", "replace")
        info = lizard.analyze_file.analyze_source_code(path, code)
        result.nloc = info.nloc
        result.lines = code.count("\n") + (0 if code.endswith("\n") or not code else 1)
        result.functions = [
            {
                "name": f.name,
                "line": f.start_line,
                "end": f.end_line,
                "ccn": f.cyclomatic_complexity,
                "nloc": f.nloc,
                "params": f.parameter_count,
            }
            for f in info.function_list
        ]
        family = DEP_FAMILY.get(lang)
        if family is not None:
            tree = _parser(_GRAMMAR[lang]).parse(raw)
            result.parsed = _EXTRACT[family](tree.root_node)
    except Exception as exc:  # eine kaputte Datei darf den Lauf nicht abbrechen
        result.error = f"{type(exc).__name__}: {exc}"
    return result


def _batch(args: tuple[str, list[tuple[str, str]]]) -> list[FileResult]:
    root, items = args
    return [analyze_file(root, p, lang) for p, lang in items]


def analyze_all(root: Path, files: list[SourceFile], workers: int | None = None) -> dict[str, FileResult]:
    items = [(f.path, f.lang) for f in files]
    # Grammatiken vorab laden, damit Worker nicht parallel herunterladen
    for lang in {f.lang for f in files if f.lang in _GRAMMAR}:
        _parser(_GRAMMAR[lang])
    workers = workers or min(8, os.cpu_count() or 1)
    if len(items) < 150 or workers == 1:
        results = [analyze_file(str(root), p, lang) for p, lang in items]
    else:
        size = max(20, len(items) // (workers * 4))
        chunks = [(str(root), items[i : i + size]) for i in range(0, len(items), size)]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = [r for batch in pool.map(_batch, chunks) for r in batch]
    return {r.path: r for r in results}
