"""Java: Package, Imports, referenzierte Typen (für Same-Package-Kanten), Klassen."""

from __future__ import annotations

import re

from tree_sitter import Node

from .base import ClassInfo, Import, Parsed, lcom4, text, walk

_TYPE_DECLS = {
    "class_declaration",
    "interface_declaration",
    "enum_declaration",
    "record_declaration",
    "annotation_type_declaration",
}
_COHESION_DECLS = {"class_declaration", "enum_declaration", "record_declaration"}
_ACCESSOR = re.compile(r"^(get|set|is|has)([A-Z]\w*)$")


def _member_accesses(body: Node) -> set[str]:
    """Namen, die eine Methode an der eigenen Instanz nutzt (Felder und Methodenaufrufe)."""
    out: set[str] = set()
    stack = [body]
    while stack:
        n = stack.pop()
        t = n.type
        if t in ("class_body", "interface_body") and n is not body:
            continue  # anonyme/innere Klassen nicht mitzählen
        if t == "method_invocation":
            obj = n.child_by_field_name("object")
            name = n.child_by_field_name("name")
            if obj is None or obj.type == "this":
                out.add(text(name))
            stack.extend(c for c in n.children if c != name)
            continue
        if t == "field_access":
            obj = n.child_by_field_name("object")
            if obj is not None and obj.type == "this":
                out.add(text(n.child_by_field_name("field")))
            if obj is not None:
                stack.append(obj)
            continue
        if t == "identifier":
            out.add(text(n))
        stack.extend(n.children)
    return out


def _class_info(node: Node) -> ClassInfo | None:
    body = node.child_by_field_name("body")
    if body is None:
        return None
    members = list(body.named_children)
    for m in list(members):
        if m.type == "enum_body_declarations":
            members.extend(m.named_children)
    fields: set[str] = set()
    methods: dict[str, set[str]] = {}
    if node.type == "record_declaration":
        params = node.child_by_field_name("parameters")
        for p in params.named_children if params else []:
            fields.add(text(p.child_by_field_name("name")))
    for m in members:
        if m.type == "field_declaration":
            for d in m.children_by_field_name("declarator"):
                fields.add(text(d.child_by_field_name("name")))
        elif m.type == "method_declaration":
            b = m.child_by_field_name("body")
            if b is not None:
                methods.setdefault(text(m.child_by_field_name("name")), set()).update(_member_accesses(b))
    # Getter/Setter zu einem Feld zerfallen sonst je in eine eigene Gruppe (bekanntes LCOM4-Artefakt):
    # sie fallen als Knoten weg, ein Aufruf zählt als Zugriff auf das Feld.
    accessor_field: dict[str, str] = {}
    for name in methods:
        m = _ACCESSOR.match(name)
        if m and (m.group(2)[:1].lower() + m.group(2)[1:]) in fields:
            accessor_field[name] = m.group(2)[:1].lower() + m.group(2)[1:]
    methods = {
        name: {accessor_field.get(a, a) for a in acc} for name, acc in methods.items() if name not in accessor_field
    }
    if len(methods) < 2 or not fields:  # zustandslose Klassen: LCOM4 nicht aussagekräftig
        return None
    lcom, groups, isolated = lcom4(fields, methods)
    return ClassInfo(
        name=text(node.child_by_field_name("name")),
        line=node.start_point[0] + 1,
        methods=len(methods),
        fields=len(fields),
        lcom=lcom,
        groups=groups,
        isolated=isolated,
    )


def extract(root: Node) -> Parsed:
    parsed = Parsed()
    refs: set[str] = set()
    for node in walk(root):
        t = node.type
        if t == "package_declaration":
            target = next((c for c in node.named_children if c.type in ("scoped_identifier", "identifier")), None)
            parsed.package = text(target)
        elif t == "import_declaration":
            target = next((c for c in node.named_children if c.type in ("scoped_identifier", "identifier")), None)
            if target is None:
                continue
            kinds = {c.type for c in node.children}
            kind = "wildcard" if "asterisk" in kinds else ("static-member" if "static" in kinds else "static")
            parsed.imports.append(Import(text(target), None, kind))
        elif t == "type_identifier":
            refs.add(text(node))
        elif t == "identifier":
            s = text(node)
            if s[:1].isupper():
                refs.add(s)
        elif t in _TYPE_DECLS:
            parsed.type_count += 1
            mods = next((c for c in node.children if c.type == "modifiers"), None)
            if t == "interface_declaration" or (mods is not None and "abstract" in text(mods).split()):
                parsed.abstract_count += 1
            if node.parent is not None and node.parent.type == "program":
                parsed.declared_types.append(text(node.child_by_field_name("name")))
            if t in _COHESION_DECLS:
                info = _class_info(node)
                if info is not None:
                    parsed.classes.append(info)
    parsed.referenced_types = sorted(refs - set(parsed.declared_types))
    return parsed
