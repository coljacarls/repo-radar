"""Python: Modul-Index über Paketwurzeln, absolute und relative Imports."""

from __future__ import annotations

import posixpath
import sys

from ..langs.base import Import

_STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def _module_name(path: str, root: str) -> str:
    rel = path[len(root) + 1 :] if root else path
    rel = rel[:-3] if rel.endswith(".py") else rel
    parts = rel.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


class PythonResolver:
    def __init__(self, py_files: list[str], tracked: set[str]):
        def chain_root(path: str) -> str:
            d = posixpath.dirname(path)
            while d and posixpath.join(d, "__init__.py") in tracked:
                d = posixpath.dirname(d)
            return d

        roots: list[str] = []
        for f in py_files:
            r = chain_root(f)
            if r not in roots:
                roots.append(r)
        for p in sorted(tracked):
            if posixpath.basename(p) in ("pyproject.toml", "setup.py", "setup.cfg"):
                d = posixpath.dirname(p)
                for cand in (posixpath.join(d, "src") if d else "src", d):
                    if cand not in roots:
                        roots.append(cand)
        for cand in ("src", ""):
            if cand not in roots:
                roots.append(cand)

        self.index: dict[str, str] = {}
        self.module_of: dict[str, str] = {}
        for f in py_files:
            own = chain_root(f)
            self.module_of[f] = _module_name(f, own)
        for root in roots:
            for f in py_files:
                if root and not f.startswith(root + "/"):
                    continue
                self.index.setdefault(_module_name(f, root), f)

    def _find(self, dotted: str) -> str | None:
        parts = dotted.split(".")
        for k in range(len(parts), 0, -1):
            hit = self.index.get(".".join(parts[:k]))
            if hit:
                return hit
        return None

    def resolve(self, path: str, imp: Import) -> tuple[set[str], set[str], int]:
        if imp.level:
            mod = self.module_of.get(path, "")
            parts = mod.split(".") if mod else []
            pkg = parts if path.endswith("__init__.py") else parts[:-1]
            up = imp.level - 1
            if up > len(pkg):
                return set(), set(), 1
            base_parts = pkg[: len(pkg) - up] + ([imp.spec] if imp.spec else [])
            base = ".".join(p for p in base_parts if p)
        else:
            base = imp.spec
        targets: set[str] = set()
        need_base = imp.names is None
        for name in imp.names or []:
            sub = f"{base}.{name}" if base else name
            if sub in self.index:
                targets.add(self.index[sub])
            else:
                need_base = True
        if need_base and base:
            hit = self.index.get(base) if imp.level else self._find(base)
            if hit:
                targets.add(hit)
            elif not targets:
                top = base.split(".")[0]
                if imp.level:
                    return set(), set(), 1
                if top in _STDLIB:
                    return set(), set(), 0
                return set(), {top}, 0
        targets.discard(path)
        return targets, set(), 0
