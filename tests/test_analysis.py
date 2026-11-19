"""End-to-End-Tests der Pipeline gegen kleine, im Test erzeugte Git-Repos."""

from repo_radar.config import load_config
from repo_radar.pipeline import run
from repo_radar.source import open_source


def analyze(repo, since: str = "all") -> dict:
    cfg = load_config(None)
    cfg["analysis"]["duplication"] = False
    cfg["history"]["since"] = since
    return run(open_source(str(repo.root)), cfg, log=lambda _m: None, workers=1)


def edges(data: dict) -> set[tuple[str, str]]:
    files = data["files"]
    return {(files[a]["path"], files[b]["path"]) for a, b, _ in data["edges"]}


def weak_edges(data: dict) -> set[tuple[str, str]]:
    files = data["files"]
    return {(files[a]["path"], files[b]["path"]) for a, b, w in data["edges"] if w}


def cycles(data: dict) -> list[set[str]]:
    return [{data["files"][i]["path"] for i in c} for c in data["cycles"]]


def file(data: dict, path: str) -> dict:
    return next(f for f in data["files"] if f["path"] == path)


# ---------------------------------------------------------------------------- TypeScript


TS_FILES = {
    "tsconfig.base.json": """{
      // Nx-typisch: Aliase in der Basis-Config, mit Kommentar und trailing comma
      "compilerOptions": { "baseUrl": ".", "paths": { "@acme/lib": ["libs/lib/src/index.ts"], "@app/*": ["apps/web/src/*"], } }
    }""",
    "apps/web/tsconfig.json": '{ "extends": "../../tsconfig.base.json" }',
    "libs/lib/tsconfig.json": '{ "extends": "../../tsconfig.base.json" }',
    "libs/lib/src/index.ts": "export * from './a';\nexport { B as Bee } from './b';\n",
    "libs/lib/src/a.ts": "export class A {}\n",
    "libs/lib/src/b.ts": "export const B = 1;\n",
    "apps/web/src/main.ts": (
        "import { A } from '@acme/lib';\n"
        "import { helper } from '@app/util/helper';\n"
        "import { Component } from '@angular/core';\n"
        "import * as fs from 'node:fs';\n"
        "export const routes = [{ loadComponent: () => import('./lazy.page').then(m => m.Lazy) }];\n"
        "export function main() { return new A() && helper(); }\n"
    ),
    "apps/web/src/util/helper.js": "export function helper() { return 1; }\n",
    "apps/web/src/lazy.page.ts": "import { main } from './main';\nexport class Lazy { x = main; }\n",
    "apps/web/src/cyc/x.ts": "import { y } from './y';\nexport const x = () => y();\n",
    "apps/web/src/cyc/y.ts": "import { z } from './z';\nexport const y = () => z();\n",
    "apps/web/src/cyc/z.ts": "import { x } from './x';\nexport const z = () => x();\n",
    "apps/web/src/types/p.ts": "import type { Q } from './q';\nexport interface P { q: Q }\n",
    "apps/web/src/types/q.ts": "import { type P } from './p';\nexport interface Q { p?: P }\n",
    "apps/web/src/store.ts": """export class Store {
  private items: string[] = [];
  private theme = 'light';
  readonly count = computed(() => this.items.length);
  add(i: string) { this.items.push(i); }
  clear() { this.items = []; }
  setTheme(t: string) { this.theme = t; }
  isDark() { return this.theme === 'dark'; }
  get size() { return this.items.length; }
  format(x: number) { return String(x); }
}
""",
    "apps/web/src/main.spec.ts": "import { main } from './main';\ndescribe('m', () => it('x', () => main()));\n",
}


def test_typescript_resolution_aliases_barrels_and_lazy(repo):
    repo.commit(TS_FILES)
    data = analyze(repo)
    e = edges(data)
    main = "apps/web/src/main.ts"
    # Barrel wird bis zur definierenden Datei durchgereicht (nur A, nicht B)
    assert (main, "libs/lib/src/a.ts") in e
    assert (main, "libs/lib/src/b.ts") not in e
    assert (main, "libs/lib/src/index.ts") not in e
    # Wildcard-Alias und .js-Datei
    assert (main, "apps/web/src/util/helper.js") in e
    # Lazy-Import ist eine schwache Kante
    assert (main, "apps/web/src/lazy.page.ts") in weak_edges(data)
    # Barrel selbst hängt an seinen Re-Exporten
    assert ("libs/lib/src/index.ts", "libs/lib/src/b.ts") in e
    assert file(data, "libs/lib/src/index.ts")["barrel"] is True
    # externe Pakete, Node-Builtins ignoriert
    assert file(data, main)["ext"] == ["@angular/core"]
    assert file(data, main)["unresolved"] == 0
    # Projekte aus tsconfig-Ordnern? Nein: Projekte kommen aus project.json/package.json
    assert file(data, main)["project"] == "."


def test_typescript_cycles_ignore_type_only_and_lazy(repo):
    repo.commit(TS_FILES)
    data = analyze(repo)
    cyc = cycles(data)
    assert {"apps/web/src/cyc/x.ts", "apps/web/src/cyc/y.ts", "apps/web/src/cyc/z.ts"} in cyc
    # Typ-Importe (p <-> q) und Lazy-Import (main -> lazy -> main) bilden keinen Zyklus
    assert not any("apps/web/src/types/p.ts" in c for c in cyc)
    assert not any("apps/web/src/main.ts" in c for c in cyc)
    assert ("apps/web/src/types/p.ts", "apps/web/src/types/q.ts") in weak_edges(data)


def test_typescript_lcom4(repo):
    repo.commit(TS_FILES)
    store = file(analyze(repo), "apps/web/src/store.ts")["classes"][0]
    # items-Gruppe (add, clear, count) und theme-Gruppe (setTheme, isDark); format() ohne Instanzbezug
    assert store["lcom"] == 2
    assert store["isolated"] == ["format()"]
    assert not any("size()" in m for g in store["groups"] for m in g)  # Accessor ignoriert
    assert any("count" in g and "add()" in g for g in store["groups"])


def test_grade_findings_carry_fields_for_agent_prompt(repo):
    """Der KI-Prompt im Report baut auf diesen Feldern der Top-Befunde auf (report/prompt.js)."""
    repo.commit(TS_FILES)
    repo.commit({"apps/web/src/cyc/x.ts": "import { y } from './y';\nexport const x = () => y() + 1;\n"}, author=("Alan", "alan@example.com"))
    grades = {g["key"]: g for g in analyze(repo)["grades"]}
    fn = grades["complexity"]["top"][0]
    assert fn["line"] <= fn["end"] and fn["nloc"] > 0
    assert grades["unit_size"]["top"][0]["ccn"] >= 1
    assert {"ca", "ce"} <= set(grades["coupling"]["top"][0])
    assert grades["cycles"]["top"][0]["cycle"] == 0
    solo = grades["knowledge"]["top"]
    assert solo and all(t["share"] >= 0.9 for t in solo)
    assert "apps/web/src/cyc/x.ts" not in {t["file"] for t in solo}  # zwei Autoren je ein Commit


def test_test_files_are_flagged_and_excluded_from_metrics(repo):
    repo.commit(TS_FILES)
    data = analyze(repo)
    spec = file(data, "apps/web/src/main.spec.ts")
    assert spec["test"] is True
    assert spec["ca"] is None  # Graph-Metriken nur für Produktivcode
    assert ("apps/web/src/main.spec.ts", "apps/web/src/main.ts") in edges(data)


# ---------------------------------------------------------------------------- Java


def test_java_same_package_wildcard_and_external(repo):
    repo.commit(
        {
            "pom.xml": "<project/>",
            "src/main/java/com/acme/app/Foo.java": (
                "package com.acme.app;\n"
                "import com.acme.util.Baz;\n"
                "import com.acme.model.*;\n"
                "import org.springframework.stereotype.Service;\n"
                "import java.util.List;\n"
                "@Service public class Foo { private Bar bar; private Baz baz; Item item; List<String> l;\n"
                "  public Bar getBar() { return bar; }\n"
                "  void a() { bar.run(); } void b() { getBar().run(); } void c() { baz.go(); }\n"
                "}\n"
            ),
            "src/main/java/com/acme/app/Bar.java": "package com.acme.app;\npublic class Bar { void run() {} }\n",
            "src/main/java/com/acme/util/Baz.java": "package com.acme.util;\npublic interface Baz { void go(); }\n",
            "src/main/java/com/acme/model/Item.java": "package com.acme.model;\npublic abstract class Item {}\n",
            "src/main/java/com/acme/model/Unused.java": "package com.acme.model;\npublic class Unused {}\n",
        }
    )
    data = analyze(repo)
    e = edges(data)
    foo = "src/main/java/com/acme/app/Foo.java"
    assert (foo, "src/main/java/com/acme/app/Bar.java") in e  # gleiches Package, ohne Import
    assert (foo, "src/main/java/com/acme/util/Baz.java") in e
    assert (foo, "src/main/java/com/acme/model/Item.java") in e  # über Wildcard
    assert (foo, "src/main/java/com/acme/model/Unused.java") not in e
    f = file(data, foo)
    assert f["ext"] == ["org.springframework.stereotype"]
    assert f["unresolved"] == 0
    # Getter getBar() zählt als Zugriff auf bar: a() und b() hängen zusammen, c() nutzt baz
    cls = f["classes"][0]
    assert cls["lcom"] == 2
    assert sorted(len(g) for g in cls["groups"]) == [2, 3]
    pkgs = {p["name"]: p for p in data["packages"]["groups"]}
    assert pkgs["src/main/java/com/acme/model"]["abstractness"] == 0.5


# ---------------------------------------------------------------------------- Python


def test_python_relative_imports_and_type_checking(repo):
    repo.commit(
        {
            "pyproject.toml": "[project]\nname='x'\n",
            "src/pkg/__init__.py": "from .core import run\n",
            "src/pkg/core.py": (
                "from typing import TYPE_CHECKING\n"
                "import requests\nimport os.path\n"
                "from . import util\nfrom .sub.deep import thing\n"
                "if TYPE_CHECKING:\n    from .models import Model\n"
                "def run():\n    from .late import later\n    return util.x\n"
            ),
            "src/pkg/util.py": "x = 1\n",
            "src/pkg/models.py": "from .core import run\nclass Model: pass\n",
            "src/pkg/late.py": "def later(): pass\n",
            "src/pkg/sub/__init__.py": "",
            "src/pkg/sub/deep.py": "from ..util import x\nthing = x\n",
            "tests/test_core.py": "from pkg.core import run\n",
        }
    )
    data = analyze(repo)
    e = edges(data)
    core = "src/pkg/core.py"
    assert (core, "src/pkg/util.py") in e
    assert (core, "src/pkg/sub/deep.py") in e
    assert ("src/pkg/sub/deep.py", "src/pkg/util.py") in e
    assert ("tests/test_core.py", core) in e
    assert ("src/pkg/__init__.py", core) in e
    assert (core, "src/pkg/models.py") in weak_edges(data)
    assert (core, "src/pkg/late.py") in weak_edges(data)
    assert file(data, core)["ext"] == ["requests"]  # os ist Standardbibliothek
    # core -> models nur unter TYPE_CHECKING: kein Zyklus
    assert not any(core in c for c in cycles(data))


# ---------------------------------------------------------------------------- Historie


def test_change_coupling_hidden_and_rename_tracking(repo):
    repo.commit(
        {
            "src/api.ts": "export const api = 1;\n",
            "backend/hook.js": "module.exports = 1;\n",
            "src/use.ts": "import { api } from './api';\nexport const u = api;\n",
            "src/old_name.ts": "export const o = 1;\n",
        }
    )
    for i in range(6):
        repo.commit({"src/api.ts": f"export const api = {i};\n", "backend/hook.js": f"module.exports = {i};\n"}, msg=f"fix: api {i}")
    for i in range(6):
        repo.commit({"src/api.ts": f"export const api = {i + 10};\n", "src/use.ts": f"import {{ api }} from './api';\nexport const u = api + {i};\n"})
    repo.commit({"src/old_name.ts": "export const o = 2;\n"})
    repo.mv("src/old_name.ts", "src/new_name.ts")
    repo.commit(msg="rename")
    data = analyze(repo)
    files = data["files"]
    pairs = {(files[c["a"]]["path"], files[c["b"]]["path"]): c for c in data["coupling"]}
    hidden = pairs[("backend/hook.js", "src/api.ts")]
    assert hidden["shared"] == 7  # 6 + initialer Commit
    assert hidden["structural"] is False
    assert pairs[("src/api.ts", "src/use.ts")]["structural"] is True
    api = file(data, "src/api.ts")
    assert api["commits"] == 13
    assert api["fixes"] == 6
    assert file(data, "src/new_name.ts")["commits_all"] == 3  # Historie vor der Umbenennung zählt mit


def test_author_identities_are_merged(repo):
    repo.commit({"a.py": "x = 1\n"}, author=("Grace Hopper", "grace@example.com"))
    repo.commit({"a.py": "x = 2\n"}, author=("gracehopper", "1234+gracehopper@users.noreply.github.com"))
    repo.commit({"a.py": "x = 3\n"}, author=("Grace Hopper", "grace@example.com"))
    repo.commit({"b.py": "y = 1\n"}, author=("Alan", "alan@example.com"))
    data = analyze(repo)
    a = file(data, "a.py")
    assert a["authors"] == [["Grace Hopper", 3]] or a["authors"] == [("Grace Hopper", 3)]
    assert data["meta"]["authors_total"] == 2


# ---------------------------------------------------------------------------- Ungetrackte Dateien


def test_repo_without_commits_is_analyzed_from_worktree(repo):
    repo.write({"pkg/__init__.py": "", "pkg/a.py": "from .b import g\n\ndef f(x):\n    return g(x)\n", "pkg/b.py": "def g(x):\n    return x\n"})
    src = open_source(str(repo.root))
    assert not src.has_commits and src.untracked
    data = analyze(repo)
    assert {f["path"] for f in data["files"]} == {"pkg/__init__.py", "pkg/a.py", "pkg/b.py"}
    assert ("pkg/a.py", "pkg/b.py") in edges(data)
    assert data["meta"]["head"] == "" and data["meta"]["commits_total"] == 0
    assert all(f["commits_all"] == 0 and f["hotspot"] == 0 for f in data["files"])
    grades = {g["key"]: g for g in data["grades"]}
    assert grades["change_coupling"]["grade"] is None
    assert grades["knowledge"]["grade"] is None and "Keine Commits" in grades["knowledge"]["value"]


def test_untracked_files_only_with_flag_and_respecting_gitignore(repo):
    repo.commit({".gitignore": "build/\n", "a.py": "import b\n", "b.py": "X = 1\n"})
    repo.write({"c.py": "import a\n", "build/gen.py": "Y = 2\n"})
    cfg = load_config(None)
    cfg["analysis"]["duplication"] = False
    cfg["history"]["since"] = "all"

    tracked = run(open_source(str(repo.root)), cfg, log=lambda _m: None, workers=1)
    assert {f["path"] for f in tracked["files"]} == {"a.py", "b.py"}

    data = run(open_source(str(repo.root), untracked=True), cfg, log=lambda _m: None, workers=1)
    assert {f["path"] for f in data["files"]} == {"a.py", "b.py", "c.py"}
    assert ("c.py", "a.py") in edges(data)
    assert file(data, "c.py")["commits_all"] == 0 and file(data, "a.py")["commits_all"] == 1
    assert data["meta"]["untracked"] is True
