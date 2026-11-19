"""Führt alle Analyseschritte aus und baut das JSON-Modell für den Report."""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__, duplication, git_history, graph_metrics, scoring
from .deps import build_graph
from .inventory import build_inventory
from .parsing import analyze_all
from .source import RepoSource, list_tracked_files

SCHEMA_VERSION = 1


def _log_norm(values: dict[str, float]) -> dict[str, float]:
    top = max(values.values(), default=0)
    if top <= 0:
        return dict.fromkeys(values, 0.0)
    return {k: math.log1p(v) / math.log1p(top) for k, v in values.items()}


def run(src: RepoSource, cfg: dict, log: Callable[[str], None] = print, workers: int | None = None) -> dict:
    timings: dict[str, float] = {}

    def step(name: str, t0: float) -> None:
        timings[name] = round(time.time() - t0, 2)
        log(f"  {name}: {timings[name]} s")

    t = time.time()
    tracked = list_tracked_files(src)
    inv = build_inventory(src.root, tracked, cfg)
    log(f"  {len(inv.files)} Quelldateien von {len(tracked)} {'gelisteten' if src.untracked else 'getrackten'} Dateien")
    step("inventory", t)
    if not inv.files:
        raise RuntimeError("Keine analysierbaren Quelldateien gefunden.")

    t = time.time()
    results = analyze_all(src.root, inv.files, workers)
    step("parsing", t)

    t = time.time()
    parsed = {p: r.parsed for p, r in results.items() if r.parsed is not None}
    graph = build_graph(src.root, inv.files, inv.tracked, parsed, {p: len(r.functions) for p, r in results.items()})
    step("dependencies", t)

    t = time.time()
    prod_covered = [f.path for f in inv.files if not f.is_test and f.path in graph.covered]
    types = {p: (pp.type_count, pp.abstract_count) for p, pp in parsed.items()}
    nloc = {p: r.nloc for p, r in results.items()}
    gm = graph_metrics.compute(
        prod_covered,
        graph.edges,
        {f.path: f.package for f in inv.files},
        {f.path: f.project for f in inv.files},
        types,
        nloc,
    )
    step("graph", t)

    t = time.time()
    analyzed = {f.path for f in inv.files}
    hist = git_history.analyze(src, analyzed, cfg)
    prod_paths = {f.path for f in inv.files if not f.is_test}
    tf = git_history.truck_factor(
        {p: h for p, h in hist.files.items() if p in prod_paths}, cfg["grades"]["knowledge"]["owner_share"]
    )
    step("history", t)

    t = time.time()
    dup = duplication.analyze(src.root, analyzed, cfg)
    if not dup.measured:
        log(f"  Duplikation nicht gemessen: {dup.reason}")
    step("duplication", t)

    # ---- Datei-Datensätze ---------------------------------------------------
    head = src.head_time
    hot_c = _log_norm({f.path: hist.files[f.path].commits for f in inv.files})
    hot_x = _log_norm({f.path: sum(fn["ccn"] for fn in results[f.path].functions) for f in inv.files})
    files: list[dict] = []
    for f in inv.files:
        r = results[f.path]
        h = hist.files[f.path]
        m = gm.file.get(f.path)
        ccns = [fn["ccn"] for fn in r.functions]
        auth_total = sum(h.authors.values())
        main_author, main_count = h.authors.most_common(1)[0] if h.authors else (None, 0)
        p = r.parsed
        classes = [asdict(c) for c in p.classes] if p else []
        files.append(
            {
                "path": f.path,
                "lang": f.lang_name,
                "project": f.project,
                "package": f.package,
                "test": f.is_test,
                "barrel": f.path in graph.barrels,
                "deps": f.path in graph.covered,
                "nloc": r.nloc,
                "lines": r.lines,
                "functions": sorted(r.functions, key=lambda fn: -fn["ccn"]),
                "fn": len(r.functions),
                "ccn_max": max(ccns, default=0),
                "ccn_sum": sum(ccns),
                "ccn_avg": round(sum(ccns) / len(ccns), 2) if ccns else 0,
                "ca": m["ca"] if m else None,
                "ce": m["ce"] if m else None,
                "instability": round(m["instability"], 3) if m and m["instability"] is not None else None,
                "pagerank": round(m["pagerank"], 3) if m else None,
                "cycle": m["cycle"] if m else None,
                "deps_transitive": m["deps_transitive"] if m else None,
                "impact": m["impact"] if m else None,
                "ext": sorted(graph.externals.get(f.path, ())),
                "unresolved": graph.unresolved.get(f.path, 0),
                "commits": h.commits,
                "added": h.added,
                "deleted": h.deleted,
                "fixes": h.fixes,
                "months": dict(sorted(h.months.items())),
                "commits_all": h.commits_all,
                "authors": h.authors.most_common(8),
                "author_count": len(h.authors),
                "main_author": main_author,
                "main_share": round(main_count / auth_total, 3) if auth_total else None,
                "first": h.first,
                "last": h.last,
                "age_days": round((head - h.last) / 86400) if h.last else None,
                "hotspot": round(hot_c[f.path] * hot_x[f.path], 4),
                "classes": classes,
                "lcom_max": max((c["lcom"] for c in classes), default=None),
                "dup_lines": dup.dup_lines.get(f.path, 0),
                "dup_pct": round(100 * dup.dup_lines.get(f.path, 0) / r.lines, 1) if r.lines and dup.measured else None,
                "error": r.error,
            }
        )

    covered = graph.covered
    coupling = []
    for c in hist.coupling:
        if c["a"] in covered and c["b"] in covered:
            structural = (c["a"], c["b"]) in graph.edges or (c["b"], c["a"]) in graph.edges
        else:
            structural = None
        coupling.append({**c, "structural": structural})

    t = time.time()
    grades = scoring.compute(files, {"duplication": dup, "graph": gm, "history": hist, "coupling": coupling, "truck_factor": tf}, cfg)
    step("scoring", t)

    index = {f["path"]: i for i, f in enumerate(files)}
    langs: dict[str, dict] = {}
    for f in files:
        entry = langs.setdefault(f["lang"], {"files": 0, "nloc": 0})
        entry["files"] += 1
        entry["nloc"] += f["nloc"]
    ext_counter: Counter = Counter(e for f in files if not f["test"] for e in f["ext"])

    def level(lm: graph_metrics.LevelMetrics) -> dict:
        return {"groups": lm.groups, "edges": lm.edges, "cycles": lm.cycles}

    return {
        "schema": SCHEMA_VERSION,
        "meta": {
            "name": src.name,
            "url": src.url,
            "head": src.head,
            "branch": src.branch,
            "subdir": src.subdir,
            "head_time": src.head_time,
            "untracked": src.untracked,
            "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "since": hist.since,
            "since_label": str(cfg["history"]["since"]),
            "tool_version": __version__,
            "languages": langs,
            "skipped": inv.skipped,
            "projects": inv.projects,
            "timings": timings,
            "duplication": {"measured": dup.measured, "reason": dup.reason},
            "commits_total": hist.commits_total,
            "commits_window": hist.commits_window,
            "authors_total": len(hist.authors_all),
            "authors_window": len(hist.authors_window),
            "monthly": sorted(hist.monthly.items()),
            "truck_factor": tf[0],
            "propagation_cost": round(gm.propagation_cost, 4),
            "parse_errors": sum(1 for f in files if f["error"]),
            "config": {"history": cfg["history"], "grades": cfg["grades"]},
        },
        "grades": grades,
        "files": files,
        "edges": [[index[a], index[b], int(dyn)] for (a, b), dyn in sorted(graph.edges.items())],
        "cycles": [[index[p] for p in c] for c in gm.cycles],
        "packages": level(gm.packages),
        "projects": level(gm.projects),
        "coupling": [
            {"a": index[c["a"]], "b": index[c["b"]], "shared": c["shared"], "degree": c["degree"], "structural": c["structural"]}
            for c in coupling
        ],
        "clones": [{**c, "a": index[c["a"]], "b": index[c["b"]]} for c in dup.clones],
        "externals": ext_counter.most_common(60),
    }
