"""TypeScript/JavaScript: Imports, Exporte (für Barrel-Auflösung), Klassen."""

from __future__ import annotations

from tree_sitter import Node

from .base import ClassInfo, Import, Parsed, lcom4, text, walk

_DECL_TYPES = {
    "class_declaration",
    "abstract_class_declaration",
    "function_declaration",
    "generator_function_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
    "module",
    "internal_module",
}
_CLASS_TYPES = {"class_declaration", "abstract_class_declaration", "class"}
_FUNC_VALUES = {"arrow_function", "function_expression", "function"}


def _string(node: Node | None) -> str | None:
    if node is None:
        return None
    if node.type == "string":
        return text(node)[1:-1]
    if node.type == "template_string" and not any(c.type == "template_substitution" for c in node.children):
        return text(node)[1:-1]
    return None


def _binding_names(node: Node) -> list[str]:
    if node.type in ("identifier", "type_identifier"):
        return [text(node)]
    return [text(n) for n in walk(node) if n.type in ("identifier", "shorthand_property_identifier_pattern")]


def _this_accesses(node: Node) -> set[str]:
    out = set()
    for n in walk(node):
        if n.type == "member_expression":
            obj = n.child_by_field_name("object")
            if obj is not None and obj.type == "this":
                out.add(text(n.child_by_field_name("property")))
    return out


def _class_info(node: Node) -> ClassInfo | None:
    body = node.child_by_field_name("body")
    if body is None:
        return None
    fields: set[str] = set()
    methods: dict[str, set[str]] = {}
    links: dict[str, set[str]] = {}
    for m in body.named_children:
        if m.type == "method_definition":
            name = text(m.child_by_field_name("name"))
            if name == "constructor":
                params = m.child_by_field_name("parameters")
                for p in params.named_children if params else []:
                    if any(c.type in ("accessibility_modifier", "readonly", "override_modifier") for c in p.children):
                        pat = p.child_by_field_name("pattern")
                        if pat is not None:
                            fields.add(text(pat))
                continue
            if any(c.type in ("get", "set") for c in m.children):
                continue  # Accessoren verfälschen LCOM4
            fn_body = m.child_by_field_name("body")
            if fn_body is not None:
                methods.setdefault(name, set()).update(_this_accesses(fn_body))
        elif m.type in ("public_field_definition", "field_definition"):
            name = text(m.child_by_field_name("name") or m.child_by_field_name("property"))
            value = m.child_by_field_name("value")
            if value is not None and value.type in _FUNC_VALUES:
                methods.setdefault(name, set()).update(_this_accesses(value))
            else:
                fields.add(name)
                if value is not None:
                    acc = _this_accesses(value)
                    if acc:
                        links[name] = acc
    if len(methods) < 2 or not fields:  # zustandslose Klassen: LCOM4 nicht aussagekräftig
        return None
    lcom, groups, isolated = lcom4(fields, methods, links)
    name_node = node.child_by_field_name("name")
    return ClassInfo(
        name=text(name_node) or "(anonym)",
        line=node.start_point[0] + 1,
        methods=len(methods),
        fields=len(fields),
        lcom=lcom,
        groups=groups,
        isolated=isolated,
    )


def extract(root: Node) -> Parsed:
    parsed = Parsed()
    local: set[str] = set()
    named: dict[str, list[str]] = {}
    star: list[str] = []
    for node in walk(root):
        t = node.type
        if t == "import_statement":
            spec = _string(node.child_by_field_name("source"))
            if spec is None:
                continue
            names: list[str] | None = None
            type_only = any(c.type == "type" for c in node.children)
            clause = next((c for c in node.named_children if c.type == "import_clause"), None)
            if clause is not None:
                found, whole, value_import = [], False, False
                for c in clause.named_children:
                    if c.type == "identifier":
                        found.append("default")
                        value_import = True
                    elif c.type == "namespace_import":
                        whole = value_import = True
                    elif c.type == "named_imports":
                        for s in c.named_children:
                            if s.type == "import_specifier":
                                found.append(text(s.child_by_field_name("name")))
                                if not any(x.type == "type" for x in s.children):
                                    value_import = True
                names = None if whole or not found else found
                type_only = type_only or not value_import
            parsed.imports.append(Import(spec, names, "type" if type_only and clause is not None else "static"))
        elif t == "export_statement":
            spec = _string(node.child_by_field_name("source"))
            clause = next((c for c in node.named_children if c.type == "export_clause"), None)
            ns = next((c for c in node.named_children if c.type == "namespace_export"), None)
            if spec is not None:
                if clause is not None:
                    origs = []
                    for s in clause.named_children:
                        if s.type != "export_specifier":
                            continue
                        orig = text(s.child_by_field_name("name"))
                        alias = text(s.child_by_field_name("alias")) or orig
                        named[alias] = [spec, orig]
                        origs.append(orig)
                    parsed.imports.append(Import(spec, origs or None, "reexport"))
                elif ns is not None:
                    local.update(_binding_names(ns))
                    parsed.imports.append(Import(spec, None, "reexport"))
                else:
                    star.append(spec)
                    parsed.imports.append(Import(spec, None, "reexport"))
                continue
            if any(c.type == "default" for c in node.children):
                local.add("default")
            decl = node.child_by_field_name("declaration")
            if decl is not None:
                if decl.type in _DECL_TYPES:
                    n = decl.child_by_field_name("name")
                    if n is not None:
                        local.add(text(n))
                elif decl.type in ("lexical_declaration", "variable_declaration"):
                    for d in decl.named_children:
                        if d.type == "variable_declarator":
                            local.update(_binding_names(d.child_by_field_name("name")))
            if clause is not None:
                for s in clause.named_children:
                    if s.type == "export_specifier":
                        local.add(text(s.child_by_field_name("alias")) or text(s.child_by_field_name("name")))
        elif t == "call_expression":
            fn = node.child_by_field_name("function")
            if fn is None or not (fn.type == "import" or (fn.type == "identifier" and text(fn) == "require")):
                continue
            args = node.child_by_field_name("arguments")
            first = args.named_children[0] if args is not None and args.named_children else None
            spec = _string(first)
            if spec is not None:
                # require() ist in CommonJS der normale (statische) Import, nur import() lädt lazy
                parsed.imports.append(Import(spec, None, "dynamic" if fn.type == "import" else "static"))
        elif t in _CLASS_TYPES or t == "interface_declaration":
            parsed.type_count += 1
            if t in ("abstract_class_declaration", "interface_declaration"):
                parsed.abstract_count += 1
            if t in _CLASS_TYPES:
                info = _class_info(node)
                if info is not None:
                    parsed.classes.append(info)
    parsed.exports = {"local": sorted(local), "named": named, "star": star}
    return parsed
