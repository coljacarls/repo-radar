"""Git-Historie: Churn, Alter, Autoren, Fix-Commits und Change-Kopplung."""

from __future__ import annotations

import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations

from .source import RepoSource, git

_REL = re.compile(r"^\s*(\d+)\s*(d|day|days|w|week|weeks|m|month|months|y|year|years)\s*$", re.I)
_DAYS = {"d": 1, "w": 7, "m": 30.44, "y": 365.25}
_RENAME_BRACE = re.compile(r"^(.*)\{(.*) => (.*)\}(.*)$")


def parse_since(since: str, head_time: int) -> int:
    """Zeitpunkt (Unix) aus '12 months', '6m', '2y', '2025-01-01' oder 'all'."""
    s = since.strip().lower()
    if s in ("all", "", "0"):
        return 0
    m = _REL.match(s)
    if m:
        return int(head_time - int(m.group(1)) * _DAYS[m.group(2)[0]] * 86400)
    return int(datetime.fromisoformat(since).replace(tzinfo=timezone.utc).timestamp())


def parse_rename(path: str) -> tuple[str, str] | None:
    if " => " not in path:
        return None
    m = _RENAME_BRACE.match(path)
    if m:
        pre, old, new, post = m.groups()
        join = lambda mid: re.sub(r"//+", "/", f"{pre}{mid}{post}")  # noqa: E731
        return join(old), join(new)
    old, new = path.split(" => ", 1)
    return old, new


@dataclass
class FileHistory:
    commits: int = 0  # im Zeitfenster
    added: int = 0
    deleted: int = 0
    fixes: int = 0
    months: Counter = field(default_factory=Counter)
    authors: Counter = field(default_factory=Counter)  # gesamte Historie
    commits_all: int = 0
    first: int | None = None
    last: int | None = None


@dataclass
class History:
    since: int
    files: dict[str, FileHistory]
    commits_total: int
    commits_window: int
    authors_window: Counter
    authors_all: Counter
    monthly: Counter  # Commits je Monat, gesamte Historie
    coupling: list[dict]
    elapsed: float = 0.0


_NOREPLY = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.github\.com$", re.I)


def author_aliases(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
    """Führt Identitäten zusammen, die dieselbe E-Mail oder denselben normalisierten Namen tragen
    ("Colja Carls" = "coljacarls" = 123+coljacarls@users.noreply.github.com). Ergänzt .mailmap."""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def tokens(name: str, email: str) -> list[str]:
        out = []
        norm = re.sub(r"[^a-z0-9]", "", name.lower())
        if len(norm) >= 3:
            out.append("n:" + norm)
        if email and "@" in email:
            out.append("e:" + email.lower())
            m = _NOREPLY.match(email)
            if m:
                out.append("n:" + re.sub(r"[^a-z0-9]", "", m.group(1).lower()))
        return out or ["r:" + name]

    counts: Counter = Counter(pairs)
    for name, email in counts:
        toks = tokens(name, email)
        for t in toks[1:]:
            ra, rb = find(toks[0]), find(t)
            if ra != rb:
                parent[ra] = rb
    names_by_root: dict[str, Counter] = {}
    for (name, email), c in counts.items():
        names_by_root.setdefault(find(tokens(name, email)[0]), Counter())[name] += c
    display = {root: names.most_common(1)[0][0] for root, names in names_by_root.items()}
    return {(n, e): display[find(tokens(n, e)[0])] for n, e in counts}


def analyze(src: RepoSource, analyzed: set[str], cfg: dict) -> History:
    t0 = time.time()
    hcfg = cfg["history"]
    since = parse_since(str(hcfg["since"]), src.head_time)
    fix_re = re.compile(hcfg["fix_pattern"], re.I)
    max_files = int(hcfg["max_files_per_commit"])

    # Repo ohne Commits: leere Historie, alle Dateien ohne Commits/Autoren
    out = git(src.root, "log", "--no-merges", "--numstat", "-M", "--format=%x1e%H%x1f%aN%x1f%aE%x1f%ct%x1f%s", "HEAD") if src.has_commits else ""
    blocks = [b for b in out.split("\x1e") if b.strip()]
    alias = author_aliases(
        [tuple(b.partition("\n")[0].split("\x1f")[1:3]) for b in blocks if b.count("\x1f") >= 4]  # type: ignore[misc]
    )
    current: dict[str, str] = {}  # historischer Pfad -> heutiger Pfad
    files: dict[str, FileHistory] = {p: FileHistory() for p in analyzed}
    authors_window: Counter = Counter()
    authors_all: Counter = Counter()
    monthly: Counter = Counter()
    pair_counts: Counter = Counter()
    commits_total = commits_window = 0

    for block in blocks:
        header, _, body = block.partition("\n")
        parts = header.split("\x1f")
        if len(parts) < 5:
            continue
        author = alias.get((parts[1], parts[2]), parts[1])
        ts_s, subject = parts[3], parts[4]
        ts = int(ts_s)
        commits_total += 1
        month = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m")
        monthly[month] += 1
        authors_all[author] += 1
        in_window = ts >= since
        if in_window:
            commits_window += 1
            authors_window[author] += 1
        is_fix = bool(fix_re.search(subject))
        touched: set[str] = set()
        for line in body.splitlines():
            cols = line.split("\t")
            if len(cols) != 3:
                continue
            add_s, del_s, path = cols
            ren = parse_rename(path)
            if ren:
                old, new = ren
                cur = current.get(new, new)
                current[old] = cur
                path = cur
            else:
                path = current.get(path, path)
            fh = files.get(path)
            if fh is None or path in touched:
                continue
            touched.add(path)
            fh.commits_all += 1
            fh.authors[author] += 1
            fh.first = ts if fh.first is None else min(fh.first, ts)
            fh.last = ts if fh.last is None else max(fh.last, ts)
            if in_window:
                fh.commits += 1
                fh.added += int(add_s) if add_s.isdigit() else 0
                fh.deleted += int(del_s) if del_s.isdigit() else 0
                fh.months[month] += 1
                if is_fix:
                    fh.fixes += 1
        if in_window and 2 <= len(touched) <= max_files:
            for a, b in combinations(sorted(touched), 2):
                pair_counts[(a, b)] += 1

    min_shared = int(hcfg["min_shared_commits"])
    min_degree = float(hcfg["min_degree"])
    coupling = []
    for (a, b), shared in pair_counts.items():
        if shared < min_shared:
            continue
        avg = (files[a].commits + files[b].commits) / 2
        degree = shared / avg if avg else 0.0
        if degree >= min_degree:
            coupling.append({"a": a, "b": b, "shared": shared, "degree": round(degree, 3)})
    coupling.sort(key=lambda c: (-c["degree"], -c["shared"]))
    return History(
        since=since,
        files=files,
        commits_total=commits_total,
        commits_window=commits_window,
        authors_window=authors_window,
        authors_all=authors_all,
        monthly=monthly,
        coupling=coupling[:5000],
        elapsed=time.time() - t0,
    )


def truck_factor(files: dict[str, FileHistory], owner_share: float) -> tuple[int, list[str]]:
    """Vereinfachter Truck-Factor (nach Avelino et al.): wie viele Hauptautoren müssen gehen,
    bis mehr als die Hälfte der Dateien keinen Kenner mehr hat?"""
    owners: dict[str, set[str]] = {}
    for path, fh in files.items():
        total = sum(fh.authors.values())
        if total:
            owners[path] = {a for a, c in fh.authors.items() if c / total >= owner_share}
    if not owners:
        return 0, []
    removed: list[str] = []
    remaining = {p: set(o) for p, o in owners.items()}
    while True:
        orphaned = sum(1 for o in remaining.values() if not o)
        if orphaned > len(remaining) / 2:
            return len(removed), removed
        counts = Counter(a for o in remaining.values() for a in o)
        if not counts:
            return len(removed), removed
        top = counts.most_common(1)[0][0]
        removed.append(top)
        for o in remaining.values():
            o.discard(top)
