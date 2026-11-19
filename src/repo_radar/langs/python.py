"""Python: Imports und Klassen."""

from __future__ import annotations

from tree_sitter import Node

from .base import ClassInfo, Import, Parsed, lcom4, text, walk

_ABSTRACT_BASES = {"ABC", "Protocol", "ABCMeta"}


def _dotted(node: Node | None) -> str:
    if node is None:
        return ""
    if node.type == "aliased_import":
        return text(node.child_by_field_name("name"))
    return text(node)


def _self_attrs(node: Node, self_name: str) -> tuple[set[str], set[str]]:
    """(gelesene/aufgerufene Attribute, zugewiesene Attribute) von `self`."""
    used, assigned = set(), set()
    for n in walk(node):
        if n.type == "attribute":
            obj = n.child_by_field_name("object")
            if obj is not None and obj.type == "identifier" and text(obj) == self_name:
                used.add(text(n.child_by_field_name("attribute")))
        elif n.type in ("assignment", "augmented_assignment"):
            left = n.child_by_field_name("left")
            if left is not None and left.type == "attribute":
                obj = left.child_by_field_name("object")
                if obj is not None and text(obj) == self_name:
                    assigned.add(text(left.child_by_field_name("attribute")))
    return used, assigned


def _class_info(node: Node) -> tuple[ClassInfo | None, bool]:
    body = node.child_by_field_name("body")
    supers = text(node.child_by_field_name("superclasses"))
    abstract = any(b in supers for b in _ABSTRACT_BASES)
    if body is None:
        return None, abstract
    fields: set[str] = set()
    methods: dict[str, set[str]] = {}
    for child in body.named_children:
        fn, decorators = child, ""
        if child.type == "decorated_definition":
            fn = child.child_by_field_name("definition")
            decorators = " ".join(text(d) for d in child.named_children if d.type == "decorator")
            if "abstractmethod" in decorators:
                abstract = True
        if fn is not None and fn.type == "function_definition":
            params = fn.child_by_field_name("parameters")
            first = params.named_children[0] if params is not None and params.named_children else None
            self_name = text(first) if first is not None and first.type == "identifier" else "self"
            used, assigned = _self_attrs(fn, self_name)
            fields |= assigned
            name = text(fn.child_by_field_name("name"))
            accessor = "property" in decorators or ".setter" in decorators
            if name != "__init__" and "staticmethod" not in decorators and not accessor:
                methods[name] = used
        elif child.type == "expression_statement":
            for a in child.named_children:
                if a.type == "assignment":
                    left = a.child_by_field_name("left")
                    if left is not None and left.type == "identifier":
                        fields.add(text(left))
    if len(methods) < 2 or not fields:  # zustandslose Klassen: LCOM4 nicht aussagekräftig
        return None, abstract
    lcom, groups, isolated = lcom4(fields, methods)
    info = ClassInfo(
        name=text(node.child_by_field_name("name")),
        line=node.start_point[0] + 1,
        methods=len(methods),
        fields=len(fields),
        lcom=lcom,
        groups=groups,
        isolated=isolated,
    )
    return info, abstract


def _import_kind(node: Node) -> str:
    """'type' unter `if TYPE_CHECKING:`, 'dynamic' innerhalb von Funktionen, sonst 'static'."""
    p = node.parent
    while p is not None:
        if p.type == "function_definition":
            return "dynamic"
        if p.type == "if_statement" and "TYPE_CHECKING" in text(p.child_by_field_name("condition")):
            return "type"
        p = p.parent
    return "static"


def extract(root: Node) -> Parsed:
    parsed = Parsed()
    for node in walk(root):
        t = node.type
        if t == "import_statement":
            kind = _import_kind(node)
            for c in node.children_by_field_name("name"):
                parsed.imports.append(Import(_dotted(c), None, kind))
        elif t == "import_from_statement":
            mod = node.child_by_field_name("module_name")
            level, modname = 0, ""
            if mod is not None and mod.type == "relative_import":
                prefix = next((c for c in mod.children if c.type == "import_prefix"), None)
                level = len(text(prefix))
                modname = text(next((c for c in mod.children if c.type == "dotted_name"), None))
            else:
                modname = text(mod)
            wildcard = any(c.type == "wildcard_import" for c in node.children)
            names = None if wildcard else [_dotted(c) for c in node.children_by_field_name("name")]
            kind = _import_kind(node)
            parsed.imports.append(Import(modname, names or None, "wildcard" if wildcard and kind == "static" else kind, level))
        elif t == "class_definition":
            parsed.type_count += 1
            info, abstract = _class_info(node)
            if abstract:
                parsed.abstract_count += 1
            if info is not None:
                parsed.classes.append(info)
    return parsed
