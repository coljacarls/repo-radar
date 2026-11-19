"""Strukturelle Kopplung: Ca/Ce/Instabilität, Zyklen, Zentralität, Propagation Cost; auf Datei-, Package- und Projektebene."""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx


@dataclass
class LevelMetrics:
    groups: list[dict] = field(default_factory=list)
    edges: list[list] = field(default_factory=list)  # [von, nach, Anzahl Datei-Kanten]
    cycles: list[list[str]] = field(default_factory=list)


@dataclass
class GraphMetrics:
    file: dict[str, dict] = field(default_factory=dict)
    cycles: list[list[str]] = field(default_factory=list)
    propagation_cost: float = 0.0
    packages: LevelMetrics = field(default_factory=LevelMetrics)
    projects: LevelMetrics = field(default_factory=LevelMetrics)


def _pagerank(nodes: list[str], edges: list[tuple[str, str]], damping: float = 0.85, iters: int = 60) -> dict[str, float]:
    n = len(nodes)
    if n == 0:
        return {}
    out: dict[str, list[str]] = {v: [] for v in nodes}
    for a, b in edges:
        out[a].append(b)
    rank = dict.fromkeys(nodes, 1.0 / n)
    for _ in range(iters):
        sink = sum(rank[v] for v in nodes if not out[v])
        new = dict.fromkeys(nodes, (1 - damping) / n + damping * sink / n)
        for v in nodes:
            if out[v]:
                share = damping * rank[v] / len(out[v])
                for w in out[v]:
                    new[w] += share
        rank = new
    return rank


def _reach_counts(g: nx.DiGraph) -> dict[str, int]:
    """Anzahl transitiv erreichbarer Knoten je Knoten (ohne sich selbst), per SCC-Kondensation und Bitmasken."""
    cond = nx.condensation(g)
    index = {v: i for i, v in enumerate(g.nodes)}
    reach: dict[int, int] = {}
    for c in reversed(list(nx.topological_sort(cond))):
        mask = 0
        for v in cond.nodes[c]["members"]:
            mask |= 1 << index[v]
        for succ in cond.successors(c):
            mask |= reach[succ]
        reach[c] = mask
    mapping = cond.graph["mapping"]
    return {v: reach[mapping[v]].bit_count() - 1 for v in g.nodes}


def _sccs(g: nx.DiGraph) -> list[list[str]]:
    return sorted(
        (sorted(c) for c in nx.strongly_connected_components(g) if len(c) > 1),
        key=lambda c: (-len(c), c[0]),
    )


def _level(
    prod: list[str],
    edges: list[tuple[str, str]],
    static_edges: list[tuple[str, str]],
    group_of: dict[str, str],
    types: dict[str, tuple[int, int]],
    nloc: dict[str, int],
) -> LevelMetrics:
    names = sorted({group_of[f] for f in prod})
    members: dict[str, list[str]] = {n: [] for n in names}
    for f in prod:
        members[group_of[f]].append(f)
    weights: dict[tuple[str, str], int] = {}
    ca_files: dict[str, set[str]] = {n: set() for n in names}
    ce_files: dict[str, set[str]] = {n: set() for n in names}
    for a, b in edges:
        ga, gb = group_of[a], group_of[b]
        if ga == gb:
            continue
        weights[(ga, gb)] = weights.get((ga, gb), 0) + 1
        ce_files[ga].add(b)
        ca_files[gb].add(a)
    g = nx.DiGraph()
    g.add_nodes_from(names)
    g.add_edges_from((group_of[a], group_of[b]) for a, b in static_edges if group_of[a] != group_of[b])
    cycles = _sccs(g)
    cycle_of = {n: i for i, c in enumerate(cycles) for n in c}
    groups = []
    for n in names:
        ca, ce = len(ca_files[n]), len(ce_files[n])
        t_total = sum(types.get(f, (0, 0))[0] for f in members[n])
        t_abs = sum(types.get(f, (0, 0))[1] for f in members[n])
        inst = ce / (ca + ce) if ca + ce else None
        abstr = t_abs / t_total if t_total else None
        groups.append(
            {
                "name": n,
                "files": len(members[n]),
                "nloc": sum(nloc.get(f, 0) for f in members[n]),
                "ca": ca,
                "ce": ce,
                "instability": inst,
                "abstractness": abstr,
                "distance": abs(abstr + inst - 1) if inst is not None and abstr is not None else None,
                "cycle": cycle_of.get(n),
            }
        )
    return LevelMetrics(groups=groups, edges=[[a, b, w] for (a, b), w in sorted(weights.items())], cycles=cycles)


def compute(
    prod_files: list[str],
    edges: dict[tuple[str, str], bool],
    package_of: dict[str, str],
    project_of: dict[str, str],
    types: dict[str, tuple[int, int]],
    nloc: dict[str, int],
) -> GraphMetrics:
    prod = set(prod_files)
    all_e = [(a, b) for (a, b) in edges if a in prod and b in prod]
    static_e = [(a, b) for (a, b), dyn in edges.items() if not dyn and a in prod and b in prod]

    g = nx.DiGraph()
    g.add_nodes_from(prod_files)
    g.add_edges_from(static_e)
    cycles = _sccs(g)
    cycle_of = {f: i for i, c in enumerate(cycles) for f in c}
    deps_t = _reach_counts(g)
    impact = _reach_counts(g.reverse(copy=False))
    n = len(prod_files)
    pc = sum(deps_t.values()) + n
    pc = pc / (n * n) if n else 0.0

    ca: dict[str, int] = dict.fromkeys(prod_files, 0)
    ce: dict[str, int] = dict.fromkeys(prod_files, 0)
    for a, b in all_e:
        ce[a] += 1
        ca[b] += 1
    pr = _pagerank(prod_files, all_e)
    file_metrics = {}
    for f in prod_files:
        tot = ca[f] + ce[f]
        file_metrics[f] = {
            "ca": ca[f],
            "ce": ce[f],
            "instability": ce[f] / tot if tot else None,
            "pagerank": pr.get(f, 0.0) * n,  # 1.0 = Durchschnitt
            "cycle": cycle_of.get(f),
            "deps_transitive": deps_t[f],
            "impact": impact[f],
        }
    return GraphMetrics(
        file=file_metrics,
        cycles=cycles,
        propagation_cost=pc,
        packages=_level(prod_files, all_e, static_e, package_of, types, nloc),
        projects=_level(prod_files, all_e, static_e, project_of, types, nloc),
    )
