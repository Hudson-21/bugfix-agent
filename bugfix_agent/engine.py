"""A bounded state machine: baseline → locate → reproduce → fix → verify → review."""

from datetime import datetime, timezone
import json
from pathlib import Path
import time

from bugfix_agent.runner import run_tests
from bugfix_agent.report import write_report
from bugfix_agent.workspace import REGRESSION, Workspace


def run(source: Path, issue: str, provider, output: Path, max_attempts=2, on_event=None) -> dict:
    source, output = Path(source).resolve(), Path(output).resolve()
    if not isinstance(issue, str) or not issue.strip() or len(issue) > 8000:
        raise ValueError("问题描述必须为 1 至 8000 个字符。")
    if max_attempts not in (1, 2):
        raise ValueError("修复轮数只能为 1 或 2。")
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("运行输出目录与输入仓库不能互相包含。")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {
        "id": output.name, "issue": issue, "source": str(source), "output": str(output),
        "mode": provider.mode, "model": provider.model, "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "events": [], "attempts": [], "baseline": None, "reproduction": None,
        "error": None, "diff": "", "max_attempts": max_attempts,
    }
    workspace = None

    def step(name, action):
        event = {"stage": name, "status": "running"}
        report["events"].append(event)
        now = time.monotonic()
        if on_event:
            on_event(dict(event))
        try:
            value = action()
            event.update(status="passed", data=value)
            return value
        except Exception as exc:
            event.update(status="failed", error=str(exc))
            raise
        finally:
            event["duration"] = round(time.monotonic() - now, 3)
            if on_event:
                on_event(dict(event))

    def fail(message):
        if report["events"]:
            report["events"][-1].update(status="failed", error=message)
        raise ValueError(message)

    def execute(targets):
        result = run_tests(workspace.root, targets, output / "logs")
        workspace.check_integrity()
        return result.to_dict()

    try:
        workspace = Workspace(source, output)
        report["baseline"] = step("baseline", lambda: execute(["."]))
        if not report["baseline"]["passed"]:
            fail("基线测试必须全部通过且至少有一个测试；本版不处理已有失败或跳过测试的仓库。")
        located = step("locator", lambda: provider.complete("locator", {
            "issue": issue, "inventory": workspace.inventory(),
        }))
        allowed = located.get("files")
        sources = workspace.read_sources(allowed)
        generated = step("tester", lambda: provider.complete("tester", {
            "issue": issue, "source": sources, "existing_tests": workspace.tests(),
        }))
        workspace.add_regression(generated.get("test_source"))
        report["reproduction"] = step("reproduction", lambda: execute([REGRESSION]))
        red = report["reproduction"]
        if not (red["returncode"] == 1 and red["failed"] > 0 and red["errors"] == 0
                and red["skipped"] == 0 and not red["timed_out"]
                and red["assertion_failures"] == red["failed"]):
            fail("新测试未通过断言失败复现问题；导入错误、异常、跳过或已通过均不算复现。")
        feedback = None
        for number in range(1, max_attempts + 1):
            attempt = {"number": number}
            report["attempts"].append(attempt)
            try:
                fix = step(f"fixer:{number}", lambda: provider.complete("fixer", {
                    "issue": issue, "source": workspace.read_sources(allowed),
                    "existing_tests": workspace.tests(), "regression_test": generated["test_source"],
                    "reproduction_log": red["log"], "previous_feedback": feedback,
                }))
                attempt["summary"] = fix.get("summary", "")
                step(f"patch:{number}", lambda: workspace.apply_edits(fix.get("edits"), allowed))
                attempt["tests"] = step(f"verification:{number}", lambda: execute(["."]))
                result = attempt["tests"]
                minimum = report["baseline"]["tests"] + red["tests"]
                if not result["passed"] or result["tests"] < minimum:
                    feedback = {"reason": "修复后测试未全部通过，或测试数量减少。", "tests": result}
                    attempt["error"] = feedback["reason"]
                    report["events"][-1]["status"] = "failed"
                    continue
                review = step(f"reviewer:{number}", lambda: provider.complete("reviewer", {
                    "issue": issue, "source": workspace.read_sources(allowed),
                    "existing_tests": workspace.tests(), "regression_test": generated["test_source"],
                    "diff": workspace.diff(), "test_result": result, "reproduction": red,
                }))
                if (type(review.get("approved")) is not bool
                        or not isinstance(review.get("findings"), list)
                        or not review["findings"]
                        or not all(isinstance(item, str) for item in review["findings"])):
                    fail("Reviewer 响应格式无效：需要布尔 approved 与非空 findings 列表。")
                attempt["review"] = review
                if review["approved"]:
                    report["status"] = "success"
                    break
                feedback = {"reason": "审查未通过", "findings": review["findings"]}
                attempt["error"] = "测试通过，但审查未通过。"
                report["events"][-1]["status"] = "failed"
            except (ValueError, RuntimeError) as exc:
                attempt["error"] = str(exc)
                feedback = {"reason": str(exc)}
        if report["status"] != "success":
            report["status"] = "failed"
            report["error"] = f"已达到 {max_attempts} 轮修复上限，需要人工检查。"
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        if report["events"]:
            report["events"][-1]["status"] = "failed"
    finally:
        report["duration"] = round(time.monotonic() - started, 3)
        report["usage"] = dict(provider.usage)
        if workspace:
            report["diff"] = workspace.diff()
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "patch.diff").write_text(report["diff"], encoding="utf-8", newline="")
        write_report(report, output)
    return report
