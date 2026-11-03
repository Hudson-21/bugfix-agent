from pathlib import Path

import pytest

from bugfix_agent.engine import run


class ScriptedProvider:
    mode = "replay"
    model = "test-fixture"
    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def __init__(self, test_code=None, edits=None, approve=True, broken_api=False):
        self.test_code = test_code or "from calc import add\ndef test_regression():\n    assert add(2, 1) == 3\n"
        self.edits = edits or [{"path": "calc.py", "search": "a - b", "replace": "a + b"}]
        self.approve = approve
        self.broken_api = broken_api

    def complete(self, role, context):
        if self.broken_api:
            raise RuntimeError("model is unavailable")
        return {
            "locator": {"files": ["calc.py"], "reason": "wrong operator"},
            "tester": {"test_source": self.test_code, "reason": "2 + 1 must be 3"},
            "fixer": {"edits": self.edits, "summary": "correct arithmetic"},
            "reviewer": {"approved": self.approve, "findings": ["checked behavior"]},
        }[role]


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    (path / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (path / "test_calc.py").write_text(
        "from calc import add\ndef test_zero():\n    assert add(3, 0) == 3\n", encoding="utf-8")
    return path


def test_real_red_green_loop_preserves_original_and_exports_evidence(repo, tmp_path):
    result = run(repo, "add should add", ScriptedProvider(), tmp_path / "out")
    assert result["status"] == "success"
    assert result["mode"] == "replay"
    assert result["baseline"]["passed"]
    assert result["reproduction"]["failed"] == 1
    assert result["attempts"][0]["tests"]["passed"]
    assert result["attempts"][0]["tests"]["tests"] == 2
    assert "a - b" in (repo / "calc.py").read_text()
    assert (tmp_path / "out" / "report.json").exists()
    assert "+    return a + b" in (tmp_path / "out" / "patch.diff").read_text()


@pytest.mark.parametrize("test_code", [
    "from calc import add\ndef test_regression():\n    assert add(2, 0) == 2\n",
    "import nonexistent_module\ndef test_regression():\n    assert False\n",
    "import pytest\n@pytest.mark.skip\ndef test_regression():\n    assert False\n",
])
def test_non_reproducing_or_invalid_test_cannot_trigger_fix(repo, tmp_path, test_code):
    result = run(repo, "add should add", ScriptedProvider(test_code=test_code), tmp_path / "out")
    assert result["status"] == "failed"
    assert result["attempts"] == []
    assert "a - b" in (tmp_path / "out" / "workspace" / "calc.py").read_text()


def test_bad_patch_stops_after_two_attempts(repo, tmp_path):
    provider = ScriptedProvider(edits=[{"path": "calc.py", "search": "a - b", "replace": "a * b"}])
    result = run(repo, "add should add", provider, tmp_path / "out")
    assert result["status"] == "failed"
    assert len(result["attempts"]) == 2


def test_review_rejection_cannot_be_success(repo, tmp_path):
    result = run(repo, "add should add", ScriptedProvider(approve=False), tmp_path / "out")
    assert result["status"] == "failed"
    assert result["attempts"][0]["tests"]["passed"]


def test_baseline_failure_stops_before_model_work(repo, tmp_path):
    (repo / "test_calc.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    result = run(repo, "fix", ScriptedProvider(broken_api=True), tmp_path / "out")
    assert result["status"] == "failed"
    assert result["baseline"]["failed"] == 1
    assert len(result["events"]) == 1


def test_model_error_still_writes_failed_report(repo, tmp_path):
    result = run(repo, "fix", ScriptedProvider(broken_api=True), tmp_path / "out")
    assert result["status"] == "failed"
    assert "model is unavailable" in result["error"]
    assert (tmp_path / "out" / "report.json").exists()


def test_fixer_cannot_weaken_existing_test(repo, tmp_path):
    provider = ScriptedProvider(edits=[{"path": "test_calc.py", "search": "3", "replace": "0"}])
    result = run(repo, "fix", provider, tmp_path / "out")
    assert result["status"] == "failed"
    assert all("error" in attempt for attempt in result["attempts"])


def test_generated_test_cannot_rewrite_source(repo, tmp_path):
    provider = ScriptedProvider(test_code=(
        "from pathlib import Path\ndef test_regression():\n"
        "    Path('calc.py').write_text('def add(a, b): return a + b')\n    assert False\n"))
    result = run(repo, "fix", provider, tmp_path / "out")
    assert result["status"] == "failed"
    assert not result["attempts"]


def test_string_approval_cannot_pass_validation(repo, tmp_path):
    result = run(repo, "fix", ScriptedProvider(approve="false"), tmp_path / "out")
    assert result["status"] == "failed"
