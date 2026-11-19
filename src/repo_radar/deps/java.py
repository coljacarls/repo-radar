"""Java: Index FQN -> Datei, Auflösung expliziter, Wildcard- und Same-Package-Referenzen."""

from __future__ import annotations

from ..langs.base import Parsed

_JDK_PREFIXES = ("java.", "javax.", "jdk.", "sun.", "com.sun.")
_TLDS = {"com", "org", "io", "net", "de", "dev", "edu", "gov", "co", "me", "info", "uk", "fr", "ch", "at"}


def _external_name(fqn: str) -> str:
    parts = fqn.split(".")
    if parts[0] in _TLDS and len(parts) >= 3:
        return ".".join(parts[:3])
    return ".".join(parts[:2])


class JavaResolver:
    def __init__(self, parsed: dict[str, Parsed]):
        self.fqn: dict[str, str] = {}
        self.pkg_types: dict[str, dict[str, str]] = {}
        for path, p in parsed.items():
            pkg = p.package or ""
            for t in p.declared_types:
                self.fqn[f"{pkg}.{t}" if pkg else t] = path
                self.pkg_types.setdefault(pkg, {})[t] = path
        # Gemeinsames Package-Präfix des Repos: unbekannte Imports darunter gelten als unaufgelöst, nicht extern
        pkgs = [k.split(".") for k in self.pkg_types if k]
        common: list[str] = []
        for parts in zip(*pkgs) if pkgs else []:
            if len(set(parts)) != 1:
                break
            common.append(parts[0])
        self.own_prefix = ".".join(common) + "." if len(common) >= 2 else None

    def _lookup(self, name: str) -> tuple[str, str] | None:
        parts = name.split(".")
        for k in range(len(parts), 0, -1):
            q = ".".join(parts[:k])
            if q in self.fqn:
                return q, self.fqn[q]
        return None

    def resolve(self, path: str, p: Parsed) -> tuple[set[str], set[str], int]:
        """(Ziel-Dateien, externe Bibliotheken, Anzahl unaufgelöster Imports)."""
        pkg = p.package or ""
        targets: set[str] = set()
        externals: set[str] = set()
        explicit: set[str] = set()
        wildcard_pkgs: list[str] = []
        unresolved = 0
        for imp in p.imports:
            if imp.kind == "wildcard" and imp.spec not in self.fqn:
                if imp.spec in self.pkg_types:
                    wildcard_pkgs.append(imp.spec)
                elif not imp.spec.startswith(_JDK_PREFIXES):
                    externals.add(_external_name(imp.spec))
                continue
            hit = self._lookup(imp.spec)
            if hit:
                targets.add(hit[1])
                explicit.add(imp.spec.split(".")[-1])
                continue
            explicit.add(imp.spec.split(".")[-1])
            if imp.spec.startswith(_JDK_PREFIXES):
                continue
            if self.own_prefix and imp.spec.startswith(self.own_prefix):
                unresolved += 1
            else:
                externals.add(_external_name(imp.spec))
        same_pkg = self.pkg_types.get(pkg, {})
        for ref in p.referenced_types:
            if ref in explicit:
                continue
            if ref in same_pkg:
                targets.add(same_pkg[ref])
                continue
            for w in wildcard_pkgs:
                hit = self.pkg_types[w].get(ref)
                if hit:
                    targets.add(hit)
                    break
        targets.discard(path)
        return targets, externals, unresolved
