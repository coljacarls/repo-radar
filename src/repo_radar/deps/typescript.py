"""Auflösung von TS/JS-Specifiern: relativ, tsconfig `paths`/`baseUrl` (inkl. `extends`), Workspace-Pakete."""

from __future__ import annotations

import json
import posixpath
import re
from pathlib import Path

_SOURCE_EXTS = [".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"]
_JS_TO_TS = {".js": [".ts", ".tsx"], ".jsx": [".tsx"], ".mjs": [".mts"], ".cjs": [".cts"]}
_NODE_BUILTINS = {
    "assert", "async_hooks", "buffer", "child_process", "cluster", "console", "constants", "crypto",
    "dgram", "dns", "domain", "events", "fs", "http", "http2", "https", "inspector", "module", "net",
    "os", "path", "perf_hooks", "process", "punycode", "querystring", "readline", "repl", "stream",
    "string_decoder", "timers", "tls", "trace_events", "tty", "url", "util", "v8", "vm", "worker_threads",
    "zlib", "test",
}  # fmt: skip


def load_jsonc(raw: str) -> object:
    out, i, n, in_str = [], 0, len(raw), False
    while i < n:
        c = raw[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(raw[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif raw.startswith("//", i):
            j = raw.find("\n", i)
            i = n if j < 0 else j
            continue
        elif raw.startswith("/*", i):
            j = raw.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return json.loads(re.sub(r",(\s*[}\]])", r"\1", "".join(out)))


def package_name(spec: str) -> str:
    parts = spec.split("/")
    return "/".join(parts[:2]) if spec.startswith("@") and len(parts) > 1 else parts[0]


class TsResolver:
    def __init__(self, root: Path, tracked: set[str]):
        self.root = root
        self.tracked = tracked
        self._configs: dict[str, dict] = {}
        self._config_for_dir: dict[str, str | None] = {}
        self._cache: dict[tuple[str, str], tuple[str, str]] = {}
        self.workspace: dict[str, str] = {}  # Paketname -> Verzeichnis
        for p in tracked:
            if posixpath.basename(p) == "package.json" and "/" in p:
                try:
                    name = json.loads((root / p).read_text(encoding="utf-8")).get("name")
                except (OSError, ValueError, AttributeError):
                    continue
                if isinstance(name, str) and name:
                    self.workspace.setdefault(name, posixpath.dirname(p))

    # ---- tsconfig -------------------------------------------------------
    def _load_config(self, path: str, depth: int = 0) -> dict:
        if path in self._configs:
            return self._configs[path]
        result: dict = {}
        self._configs[path] = result  # Schutz gegen zyklische extends
        try:
            data = load_jsonc((self.root / path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return result
        if not isinstance(data, dict):
            return result
        cdir = posixpath.dirname(path)
        extends = data.get("extends")
        for ext in [extends] if isinstance(extends, str) else (extends or []):
            if isinstance(ext, str) and ext.startswith(".") and depth < 10:
                target = posixpath.normpath(posixpath.join(cdir, ext))
                if not target.endswith(".json"):
                    target += ".json"
                if target in self.tracked:
                    result.update(self._load_config(target, depth + 1))
        opts = data.get("compilerOptions") or {}
        if isinstance(opts.get("baseUrl"), str):
            result["baseUrl"] = posixpath.normpath(posixpath.join(cdir, opts["baseUrl"]))
        if isinstance(opts.get("paths"), dict):
            result["paths"] = opts["paths"]
            result["paths_dir"] = cdir
        self._configs[path] = result
        return result

    def _config(self, file: str) -> dict:
        d = posixpath.dirname(file)
        if d in self._config_for_dir:
            cfg = self._config_for_dir[d]
            return self._configs.get(cfg, {}) if cfg else {}
        found = None
        cur = d
        while True:
            for name in ("tsconfig.json", "jsconfig.json", "tsconfig.base.json"):
                cand = posixpath.join(cur, name) if cur else name
                if cand in self.tracked:
                    found = cand
                    break
            if found or not cur:
                break
            cur = posixpath.dirname(cur)
        self._config_for_dir[d] = found
        return self._load_config(found) if found else {}

    # ---- Dateisuche -----------------------------------------------------
    def _try(self, base: str) -> str | None:
        base = posixpath.normpath(base)
        if base.startswith("..") or base == ".":
            return None
        stem, ext = posixpath.splitext(base)
        for alt in _JS_TO_TS.get(ext, []):
            if stem + alt in self.tracked:
                return stem + alt
        if base in self.tracked:
            return base
        for e in _SOURCE_EXTS:
            if base + e in self.tracked:
                return base + e
        for e in _SOURCE_EXTS:
            cand = posixpath.join(base, "index" + e)
            if cand in self.tracked:
                return cand
        return None

    def _workspace_entry(self, pkg_dir: str, sub: str) -> str | None:
        if sub:
            return self._try(posixpath.join(pkg_dir, sub)) or self._try(posixpath.join(pkg_dir, "src", sub))
        try:
            meta = json.loads((self.root / pkg_dir / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        for key in ("source", "types", "typings", "module", "main"):
            val = meta.get(key) if isinstance(meta, dict) else None
            if isinstance(val, str):
                val = re.sub(r"\.d\.ts$", "", val)
                hit = self._try(posixpath.join(pkg_dir, val))
                if hit:
                    return hit
        return self._try(posixpath.join(pkg_dir, "src", "index")) or self._try(posixpath.join(pkg_dir, "index"))

    # ---- Öffentliche API --------------------------------------------------
    def resolve(self, file: str, spec: str) -> tuple[str, str]:
        """Liefert (Art, Wert): ("file", Pfad) | ("external", Paket) | ("ignore", "") | ("unresolved", spec)."""
        key = (posixpath.dirname(file), spec)
        if key not in self._cache:
            self._cache[key] = self._resolve(file, spec)
        return self._cache[key]

    def _resolve(self, file: str, spec: str) -> tuple[str, str]:
        spec = spec.split("?")[0]
        if spec.startswith("node:") or spec in _NODE_BUILTINS or spec.split("/")[0] in _NODE_BUILTINS:
            return ("ignore", "")
        if spec.startswith((".", "/")):
            base = spec.lstrip("/") if spec.startswith("/") else posixpath.join(posixpath.dirname(file), spec)
            hit = self._try(base)
            if hit:
                return ("file", hit)
            return ("ignore", "") if posixpath.normpath(base) in self.tracked else ("unresolved", spec)
        cfg = self._config(file)
        paths = cfg.get("paths") or {}
        paths_base = cfg.get("baseUrl") or cfg.get("paths_dir") or ""
        best = None
        for pattern, subs in paths.items():
            if "*" in pattern:
                pre, post = pattern.split("*", 1)
                if spec.startswith(pre) and spec.endswith(post) and len(spec) >= len(pre) + len(post):
                    star = spec[len(pre) : len(spec) - len(post)]
                    if best is None or len(pre) > best[0]:
                        best = (len(pre), subs, star)
            elif pattern == spec and (best is None or len(pattern) > best[0]):
                best = (len(pattern), subs, "")
        if best is not None:
            for sub in best[1] if isinstance(best[1], list) else []:
                hit = self._try(posixpath.join(paths_base, sub.replace("*", best[2])))
                if hit:
                    return ("file", hit)
        if cfg.get("baseUrl") is not None:
            hit = self._try(posixpath.join(cfg["baseUrl"], spec))
            if hit:
                return ("file", hit)
        pkg = package_name(spec)
        if pkg in self.workspace:
            hit = self._workspace_entry(self.workspace[pkg], spec[len(pkg) :].lstrip("/"))
            if hit:
                return ("file", hit)
        if best is not None:
            return ("unresolved", spec)
        return ("external", pkg)
