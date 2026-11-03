from pathlib import Path
import subprocess

import pytest

from bugfix_agent.workspace import Workspace


@pytest.fixture
def workspace(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (source / "test_calc.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    (source / ".env").write_text("SECRET=not-for-context", encoding="utf-8")
    return Workspace(source, tmp_path / "run")


def test_edits_change_only_copy_and_generate_diff(workspace):
    workspace.apply_edits([{"path": "calc.py", "search": "a - b", "replace": "a + b"}], ["calc.py"])
    assert "a + b" in (workspace.root / "calc.py").read_text()
    assert "a - b" in (workspace.source / "calc.py").read_text()
    assert "+    return a + b" in workspace.diff()
    assert not (workspace.root / ".env").exists()
    assert "add(a, b)" in workspace.inventory()["calc.py"]


@pytest.mark.parametrize("path", ["../escape.py", "C:/escape.py", "/tmp/escape.py", "test_calc.py"])
def test_rejects_escape_and_test_edits(workspace, path):
    with pytest.raises(ValueError):
        workspace.apply_edits([{"path": path, "search": "True", "replace": "False"}], [path])


def test_batch_patch_is_atomic_on_invalid_second_edit(workspace):
    with pytest.raises(ValueError):
        workspace.apply_edits([
            {"path": "calc.py", "search": "a - b", "replace": "a + b"},
            {"path": "calc.py", "search": "missing", "replace": "replacement"},
        ], ["calc.py"])
    assert "a - b" in (workspace.root / "calc.py").read_text()


def test_rejects_syntax_error_and_ambiguous_search(workspace):
    for search, replace in [("a - b", "("), ("a", "x")]:
        with pytest.raises(ValueError):
            workspace.apply_edits([{"path": "calc.py", "search": search, "replace": replace}], ["calc.py"])


def test_output_cannot_be_inside_input(tmp_path):
    with pytest.raises(ValueError):
        Workspace(tmp_path, tmp_path / "runs")


def test_patch_applies_with_git_even_without_final_newline(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "calc.py").write_text("def add(a, b):\n    return a - b", encoding="utf-8")
    workspace = Workspace(source, tmp_path / "run")
    workspace.apply_edits([{"path": "calc.py", "search": "a - b", "replace": "a + b"}], ["calc.py"])
    regression = "from calc import add\ndef test_add():\n    assert add(2, 1) == 3"
    workspace.add_regression(regression)
    patch = tmp_path / "patch.diff"
    patch.write_text(workspace.diff(), encoding="utf-8", newline="\n")
    subprocess.run(["git", "init", "--quiet"], cwd=source, check=True, capture_output=True)
    result = subprocess.run(["git", "-c", "core.autocrlf=false", "apply", str(patch)],
                            cwd=source, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (source / "calc.py").read_text() == "def add(a, b):\n    return a + b"
    assert (source / "test_agent_regression.py").read_text() == regression
