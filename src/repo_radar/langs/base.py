"""Gemeinsame Typen und Helfer für die tree-sitter-Extraktoren."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from tree_sitter import Node


@dataclass
class Import:
    spec: str  # TS: Modul-Specifier, Java: FQN, Python: Modulname (ohne Punkte-Präfix)
    names: list[str] | None = None  # importierte Symbole; None = ganzes Modul
    kind: str = "static"  # static | dynamic | reexport | wildcard | static-member
    level: int = 0  # Python: Anzahl führender Punkte


@dataclass
class ClassInfo:
    name: str
    line: int
    methods: int
    fields: int
    lcom: int
    groups: list[list[str]]
    isolated: list[str] = field(default_factory=list)


@dataclass
class Parsed:
    imports: list[Import] = field(default_factory=list)
    # TS: {"local": [...], "named": {exportiert: [spec, original]}, "star": [spec]}
    exports: dict | None = None
    package: str | None = None  # Java
    declared_types: list[str] = field(default_factory=list)  # Java: Top-Level-Typen
    referenced_types: list[str] = field(default_factory=list)  # Java
    classes: list[ClassInfo] = field(default_factory=list)
    type_count: int = 0
    abstract_count: int = 0


def walk(node: Node) -> Iterator[Node]:
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def text(node: Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", "replace")


def lcom4(
    fields: set[str],
    methods: dict[str, set[str]],
    field_links: dict[str, set[str]] | None = None,
) -> tuple[int, list[list[str]], list[str]]:
    """LCOM4 nach Hitz & Montazeri: Anzahl zusammenhängender Methodengruppen.

    Zwei Methoden hängen zusammen, wenn sie ein Feld teilen oder sich gegenseitig aufrufen.
    `field_links` verbindet Felder, deren Initialisierer andere Member nutzen (z. B. Angular `computed`).
    Variante: Methoden ganz ohne Instanzbezug zählen nicht als eigene Gruppe, sie kommen in `isolated`.
    Rückgabe: (LCOM4, Gruppen, isolierte Methoden).
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for m, accessed in methods.items():
        find("m:" + m)
        for a in accessed:
            if a in methods and a != m:
                union("m:" + m, "m:" + a)
            elif a in fields:
                union("m:" + m, "f:" + a)
    for f, accessed in (field_links or {}).items():
        for a in accessed:
            if a in methods:
                union("f:" + f, "m:" + a)
            elif a in fields and a != f:
                union("f:" + f, "f:" + a)

    groups: dict[str, list[str]] = {}
    for key in list(parent):
        groups.setdefault(find(key), []).append(key)
    result, isolated = [], []
    for members in groups.values():
        if not any(k.startswith("m:") for k in members):
            continue
        if len(members) == 1:
            # Methode ohne jeden Instanzbezug (könnte statisch sein): eigene Liste, keine eigene Gruppe
            isolated.append(members[0][2:] + "()")
            continue
        result.append(sorted(k[2:] + ("()" if k.startswith("m:") else "") for k in members))
    result.sort(key=len, reverse=True)
    return max(len(result), 1), result, sorted(isolated)
