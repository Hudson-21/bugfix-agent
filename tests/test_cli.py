import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case", ["coupon", "pagination", "average"])
def test_demo_generates_real_test_evidence_and_honest_report(tmp_path, case):
    output = tmp_path / case
    result = subprocess.run([sys.executable, "-m", "bugfix_agent", "demo", "--case", case,
                             "--output", str(output)], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "success"
    assert report["mode"] == "replay" and report["usage"]["calls"] == 0
    assert report["reproduction"]["failed"] > 0
    assert report["attempts"][-1]["tests"]["passed"]
    html = (output / "report.html").read_text(encoding="utf-8")
    assert "预设响应演示" in html and "真实模型" in html
    assert (output / "PR.md").exists()


def test_live_mode_without_key_has_actionable_error(tmp_path):
    env = dict(os.environ)
    env.pop("DEEPSEEK_API_KEY", None)
    result = subprocess.run([sys.executable, "-m", "bugfix_agent", "run", "--repo", str(tmp_path),
                             "--issue", "fix"], cwd=ROOT, env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 2
    assert "DEEPSEEK_API_KEY" in result.stderr


def test_running_inside_target_repo_selects_external_output(tmp_path):
    repo = tmp_path / "input"
    repo.mkdir()
    (repo / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    env = dict(os.environ, DEEPSEEK_API_KEY="dummy-no-network-needed", PYTHONPATH=str(ROOT))
    result = subprocess.run([sys.executable, "-m", "bugfix_agent", "run", "--repo", ".", "--issue", "fix"],
                            cwd=repo, env=env, capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 1, result.stdout + result.stderr
    reports = list((tmp_path / "bugfix-agent-runs").glob("*/report.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding="utf-8"))["baseline"]["failed"] == 1


def test_prompted_key_is_not_saved_or_printed(tmp_path, monkeypatch, capsys):
    from bugfix_agent import cli

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr("getpass.getpass", lambda prompt: "local-secret-not-for-files")
    output = tmp_path / "report"
    code = cli.main(["run", "--repo", str(repo), "--issue", "fix", "--ask-key", "--output", str(output)])
    assert code == 1  # Baseline fails before any network request.
    assert "DEEPSEEK_API_KEY" not in os.environ
    captured = capsys.readouterr()
    assert "local-secret-not-for-files" not in captured.out + captured.err
    report = (output / "report.json").read_text(encoding="utf-8")
    assert "local-secret-not-for-files" not in report
    assert json.loads(report)["baseline"]["failed"] == 1


def test_replay_never_prompts_for_key(tmp_path, monkeypatch):
    from bugfix_agent import cli

    def unexpected_prompt(prompt):
        raise AssertionError("Replay must not request credentials")

    monkeypatch.setattr("getpass.getpass", unexpected_prompt)
    assert cli.main(["demo", "--ask-key", "--output", str(tmp_path / "replay")]) == 0
