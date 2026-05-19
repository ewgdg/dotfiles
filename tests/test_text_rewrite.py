from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pytest

from scripts import text_rewrite as module


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/text_rewrite.py"


def test_collapse_home_path_rewrites_exact_home_and_children() -> None:
    text = 'root=/home/tester\ncache=/home/tester/.cache\n'

    assert module.collapse_home_paths(text, home="/home/tester") == 'root=~\ncache=~/.cache\n'


def test_collapse_home_path_does_not_rewrite_similar_paths() -> None:
    text = '/home/tester-other\n/mnt/home/tester/file\n/home/tester.file\n/home/tester/file\n'

    assert module.collapse_home_paths(text, home="/home/tester") == (
        '/home/tester-other\n/mnt/home/tester/file\n/home/tester.file\n~/file\n'
    )


def test_expand_home_path_rewrites_exact_tilde_and_children() -> None:
    text = 'root=~\ncache=~/.cache\nuser=~other\nword=prefix~/.cache\n'

    assert module.expand_home_paths(text, home="/home/tester") == (
        'root=/home/tester\ncache=/home/tester/.cache\nuser=~other\nword=prefix~/.cache\n'
    )


def test_home_path_requires_safe_home() -> None:
    with pytest.raises(ValueError, match="HOME"):
        module.collapse_home_paths("/tmp", home="")
    with pytest.raises(ValueError, match="HOME"):
        module.expand_home_paths("~", home="/")


def test_literal_replace() -> None:
    assert module.apply_literal_replacement("a b a", old="a", new="x") == "x b x"


def test_regex_replace() -> None:
    assert module.apply_regex_replacement("abc123", pattern=r"\d+", replacement="#") == "abc#"


def test_cli_home_collapse_reads_stdin_and_writes_stdout(monkeypatch) -> None:
    monkeypatch.setenv("HOME", "/home/tester")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "home", "collapse"],
        input="path=/home/tester/project\nother=/home/tester-other\n",
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout == "path=~/project\nother=/home/tester-other\n"


def test_cli_replace_writes_output_path(tmp_path: Path) -> None:
    input_path = tmp_path / "input.txt"
    output_path = tmp_path / "output.txt"
    input_path.write_text("alpha beta alpha", encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "replace",
            str(input_path),
            str(output_path),
            "--literal",
            "alpha",
            "--with",
            "omega",
        ],
        check=True,
    )

    assert output_path.read_text(encoding="utf-8") == "omega beta omega"
