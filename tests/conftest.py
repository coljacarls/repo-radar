import os
import subprocess
from pathlib import Path

import pytest

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Ada",
    "GIT_AUTHOR_EMAIL": "ada@example.com",
    "GIT_COMMITTER_NAME": "Ada",
    "GIT_COMMITTER_EMAIL": "ada@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


class Repo:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self._git("init", "-q", "-b", "main")

    def _git(self, *args: str, env: dict | None = None) -> None:
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, env=env or GIT_ENV)

    def write(self, files: dict[str, str]) -> None:
        for rel, content in files.items():
            p = self.root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

    def commit(self, files: dict[str, str] | None = None, msg: str | None = None, author: tuple[str, str] | None = None) -> None:
        if files:
            self.write(files)
        self._git("add", "-A")
        self.n += 1
        env = dict(GIT_ENV)
        # feste, aufsteigende Zeitstempel innerhalb des Analysefensters
        stamp = f"@{1_780_000_000 + self.n * 3600} +0000"
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
        if author:
            env["GIT_AUTHOR_NAME"], env["GIT_AUTHOR_EMAIL"] = author
        self._git("commit", "-q", "--allow-empty", "-m", msg or f"commit {self.n}", env=env)

    def mv(self, old: str, new: str) -> None:
        self._git("mv", old, new)


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    return Repo(tmp_path / "repo")
