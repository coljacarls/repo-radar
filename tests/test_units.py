from repo_radar.config import matches_any
from repo_radar.deps.typescript import load_jsonc, package_name
from repo_radar.git_history import author_aliases, parse_rename, parse_since
from repo_radar.inventory import is_test_file
from repo_radar.langs.base import lcom4
from repo_radar.scoring import ladder_grade, profile_grade


def test_globs():
    assert matches_any("node_modules/x/y.js", ["**/node_modules/**"])
    assert matches_any("a/b/node_modules/y.js", ["**/node_modules/**"])
    assert matches_any("dist/main.js", ["**/dist/**"])
    assert not matches_any("src/distance.ts", ["**/dist/**"])
    assert matches_any("lib/x.min.js", ["**/*.min.js"])
    assert matches_any("x.min.js", ["**/*.min.js"])


def test_parse_rename():
    assert parse_rename("src/{old => new}/a.ts") == ("src/old/a.ts", "src/new/a.ts")
    assert parse_rename("src/{ => sub}/a.ts") == ("src/a.ts", "src/sub/a.ts")
    assert parse_rename("a.ts => b.ts") == ("a.ts", "b.ts")
    assert parse_rename("plain.ts") is None


def test_parse_since():
    head = 1_800_000_000
    assert parse_since("all", head) == 0
    assert head - parse_since("12 months", head) == int(12 * 30.44 * 86400)
    assert head - parse_since("2w", head) == 14 * 86400
    assert parse_since("2024-01-01", head) == 1_704_067_200


def test_jsonc_and_package_name():
    assert load_jsonc('{"a": "http://x", // c\n /* b */ "b": [1,2,],}') == {"a": "http://x", "b": [1, 2]}
    assert package_name("@scope/pkg/sub") == "@scope/pkg"
    assert package_name("rxjs/operators") == "rxjs"


def test_test_file_detection():
    assert is_test_file("src/app/x.component.spec.ts")
    assert is_test_file("tests/test_core.py")
    assert is_test_file("src/test/java/a/FooTest.java")
    assert is_test_file("pkg/core_test.go")
    assert is_test_file("src/testing/fakes.ts")  # Ordner "testing" zählt bewusst als Test
    assert not is_test_file("src/app/latest.ts")
    assert not is_test_file("src/contest/entry.ts")


def test_lcom4_groups():
    lcom, groups, isolated = lcom4({"a", "b"}, {"m1": {"a"}, "m2": {"a", "m3"}, "m3": set(), "m4": {"b"}, "m5": set()})
    assert lcom == 2
    assert isolated == ["m5()"]
    assert ["a", "m1()", "m2()", "m3()"] in groups


def test_grades():
    assert ladder_grade(0, [0, 3, 8, 15]) == "A"
    assert ladder_grade(3.1, [0, 3, 8, 15]) == "C"
    assert ladder_grade(99, [0, 3, 8, 15]) == "E"
    table = {"A": [25, 0, 0], "B": [30, 5, 0], "C": [40, 10, 0], "D": [50, 15, 5]}
    assert profile_grade([20, 0, 0], table) == "A"
    assert profile_grade([20, 0, 0.1], table) == "D"  # eine sehr komplexe Funktion deckelt die Note


def test_author_aliases():
    m = author_aliases([("Colja Carls", "c@x.de"), ("coljacarls", "1+coljacarls@users.noreply.github.com"), ("Bot", "bot@x")])
    assert m[("coljacarls", "1+coljacarls@users.noreply.github.com")] == m[("Colja Carls", "c@x.de")]
    assert m[("Bot", "bot@x")] == "Bot"
