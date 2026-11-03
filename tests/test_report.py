from bugfix_agent.report import write_report


def test_report_escapes_untrusted_issue_and_diff(tmp_path):
    report = {
        "id": "test", "mode": "replay", "model": "fixture", "status": "failed",
        "issue": '<script>alert("issue")</script>', "source": "/repo", "duration": 1,
        "started_at": "2026-11-03T10:00:00+00:00", "max_attempts": 2,
        "error": "<img src=x onerror=alert(1)>", "events": [], "attempts": [],
        "baseline": None, "reproduction": None, "usage": {"calls": 0},
        "diff": "+<script>alert('diff')</script>",
    }
    write_report(report, tmp_path)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert '<script>alert("issue")</script>' not in html
    assert "+<script>alert('diff')</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html


def test_live_mode_with_no_api_attempt_does_not_claim_model_was_called(tmp_path):
    report = {
        "id": "test", "mode": "live", "model": "deepseek-chat", "status": "failed",
        "issue": "broken", "source": "/repo", "duration": 1,
        "started_at": "2026-11-03T10:00:00+00:00", "max_attempts": 2,
        "error": "baseline failed", "events": [], "attempts": [],
        "baseline": None, "reproduction": None, "usage": {"calls": 0}, "diff": "",
    }
    write_report(report, tmp_path)
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    assert "本次已调用真实模型" not in html
    assert "尚未发起模型请求" in html
