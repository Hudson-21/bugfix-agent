from pathlib import Path
import json

import pytest

from bugfix_agent.engine import run
from bugfix_agent.provider import ReplayProvider
from bugfix_agent.runner import run_tests


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "bugfix_agent" / "cases" / "inventory"


def evaluate(workspace, logs):
    return run_tests(ROOT, ["evals/inventory", "--inventory-workspace", str(workspace)], logs)


def test_inventory_repair_preserves_original_and_passes_external_acceptance(tmp_path):
    source = CASE / "repo"
    original = {p.name: p.read_bytes() for p in source.glob("*.py")}
    issue = json.loads((CASE / "issue.json").read_text(encoding="utf-8"))["issue"]
    output = tmp_path / "repair"
    report = run(source, issue, ReplayProvider(CASE / "replay.json"), output)

    assert report["status"] == "success"
    assert report["mode"] == "replay" and report["usage"]["calls"] == 0
    assert report["baseline"]["passed"] and report["baseline"]["tests"] == 9
    assert report["reproduction"]["assertion_failures"] == 3
    assert report["attempts"][-1]["tests"]["tests"] == 12
    assert {p.name: p.read_bytes() for p in source.glob("*.py")} == original
    # External cases must not enter the model's working copy or its reported test total.
    assert {p.name for p in (output / "workspace").glob("*.py")} == {
        "inventory.py", "test_inventory.py", "test_agent_regression.py",
    }
    before_report = (output / "report.json").read_bytes()
    red = evaluate(source, tmp_path / "external-red")
    assert red.returncode == 1 and red.assertion_failures == 8
    assert red.tests == 12 and red.errors == 0 and red.skipped == 0
    green = evaluate(output / "workspace", tmp_path / "external-green")
    assert green.passed and green.tests == 12, green.log
    assert (output / "report.json").read_bytes() == before_report


@pytest.mark.parametrize("broken_fix", [
    # Successful deductions made on a copy never reach the caller.
    """def reserve(stock, lines):
    candidate = dict(stock)
    for sku, quantity in lines:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError('quantity')
        if sku not in candidate or candidate[sku] < quantity:
            raise ValueError('stock')
        candidate[sku] -= quantity
""",
    # Prechecking each line against initial stock ignores duplicate demand.
    """def reserve(stock, lines):
    for sku, quantity in lines:
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError('quantity')
        if sku not in stock or stock[sku] < quantity:
            raise ValueError('stock')
    for sku, quantity in lines:
        stock[sku] -= quantity
""",
], ids=["copy-without-commit", "precheck-without-accumulating"])
def test_external_acceptance_rejects_plausible_incomplete_fixes(tmp_path, broken_fix):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "inventory.py").write_text(broken_fix, encoding="utf-8")
    result = evaluate(workspace, tmp_path / "logs")
    assert result.returncode == 1 and result.failed > 0, result.log
    assert result.tests == 12 and result.errors == 0 and result.skipped == 0
