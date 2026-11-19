"""Baut den Datei-Abhängigkeitsgraphen aus den Extraktionsergebnissen."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..inventory import DEP_FAMILY, SourceFile
from ..langs.base import Parsed
from .java import JavaResolver
from .python import PythonResolver
from .typescript import TsResolver


@dataclass
class DepGraph:
    # (von, nach) -> True, wenn die Kante "schwach" ist: nur Lazy-Imports (import(), Imports in Funktionen)
    # oder reine Typ-Imports (`import type`, `if TYPE_CHECKING`). Schwache Kanten zählen nicht für Zyklen.
    edges: dict[tuple[str, str], bool] = field(default_factory=dict)
    externals: dict[str, set[str]] = field(default_factory=dict)
    unresolved: dict[str, int] = field(default_factory=dict)
    barrels: set[str] = field(default_factory=set)
    covered: set[str] = field(default_factory=set)  # Dateien mit Import-Auflösung

    def add(self, src: str, dst: str, dynamic: bool) -> None:
        if src == dst:
            return
        key = (src, dst)
        self.edges[key] = self.edges.get(key, True) and dynamic


def _is_barrel(p: Parsed, functions: int) -> bool:
    ex = p.exports or {}
    reexports = bool(ex.get("named") or ex.get("star"))
    return reexports and not ex.get("local") and functions == 0 and p.type_count == 0


def build_graph(
    root: Path,
    files: list[SourceFile],
    tracked: set[str],
    parsed: dict[str, Parsed],
    function_counts: dict[str, int],
) -> DepGraph:
    graph = DepGraph()
    analyzed = {f.path for f in files}
    by_family: dict[str, list[SourceFile]] = {}
    for f in files:
        fam = DEP_FAMILY.get(f.lang)
        if fam and f.path in parsed:
            by_family.setdefault(fam, []).append(f)
            graph.covered.add(f.path)

    # ---- TypeScript / JavaScript -------------------------------------------
    ts_files = by_family.get("ts", [])
    if ts_files:
        ts = TsResolver(root, tracked)
        for f in ts_files:
            if _is_barrel(parsed[f.path], function_counts.get(f.path, 0)):
                graph.barrels.add(f.path)

        def find_symbol(file: str, name: str, depth: int) -> set[str] | None:
            """Datei(en), in denen `name` letztlich definiert ist; None, wenn nicht gefunden."""
            ex = parsed[file].exports if file in parsed else None
            if ex is None or depth > 10:
                return None
            if name in ex["local"]:
                return {file}
            if name in ex["named"]:
                spec, orig = ex["named"][name]
                kind, target = ts.resolve(file, spec)
                if kind == "file" and target in analyzed:
                    return find_symbol(target, orig, depth + 1) or {target}
                return {file}
            if name != "default":
                for spec in ex["star"]:
                    kind, target = ts.resolve(file, spec)
                    if kind == "file" and target in analyzed:
                        hit = find_symbol(target, name, depth + 1)
                        if hit:
                            return hit
            return None

        for f in ts_files:
            ext: set[str] = set()
            for imp in parsed[f.path].imports:
                kind, value = ts.resolve(f.path, imp.spec)
                if kind == "external":
                    ext.add(value)
                elif kind == "unresolved":
                    graph.unresolved[f.path] = graph.unresolved.get(f.path, 0) + 1
                elif kind == "file" and value in analyzed:
                    dynamic = imp.kind in ("dynamic", "type")
                    target_ex = parsed[value].exports if value in parsed else None
                    reexports = bool(target_ex and (target_ex["named"] or target_ex["star"]))
                    if reexports and imp.names and imp.kind != "reexport":
                        for name in imp.names:
                            for t in find_symbol(value, name, 0) or {value}:
                                graph.add(f.path, t, dynamic)
                    else:
                        graph.add(f.path, value, dynamic)
            if ext:
                graph.externals[f.path] = ext

    # ---- Java ---------------------------------------------------------------
    java_files = by_family.get("java", [])
    if java_files:
        jr = JavaResolver({f.path: parsed[f.path] for f in java_files})
        for f in java_files:
            targets, ext, unresolved = jr.resolve(f.path, parsed[f.path])
            for t in targets:
                graph.add(f.path, t, False)
            if ext:
                graph.externals[f.path] = ext
            if unresolved:
                graph.unresolved[f.path] = unresolved

    # ---- Python -------------------------------------------------------------
    py_files = by_family.get("python", [])
    if py_files:
        pr = PythonResolver([f.path for f in py_files], tracked)
        for f in py_files:
            ext = set()
            for imp in parsed[f.path].imports:
                targets, e, unresolved = pr.resolve(f.path, imp)
                for t in targets:
                    graph.add(f.path, t, imp.kind in ("dynamic", "type"))
                ext |= e
                if unresolved:
                    graph.unresolved[f.path] = graph.unresolved.get(f.path, 0) + unresolved
            if ext:
                graph.externals[f.path] = ext
    return graph
