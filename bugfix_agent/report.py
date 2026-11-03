"""Portable, escaped HTML report plus a local PR draft."""

from html import escape
import json
from pathlib import Path


LABELS = {
    "baseline": "基线测试", "locator": "定位 Agent", "tester": "测试 Agent",
    "reproduction": "复现验证", "fixer": "修复 Agent", "patch": "应用补丁",
    "verification": "回归验证", "reviewer": "审查 Agent",
}


def pretty(value):
    return escape(json.dumps(value, ensure_ascii=False, indent=2))


def write_report(report: dict, output: Path):
    output = Path(output)
    live = report["mode"] == "live"
    success = report["status"] == "success"
    usage = report.get("usage", {})
    mode = "模型 API 模式" if live else "预设响应演示 · 无模型调用"
    if live:
        note = (f"已发起 {usage.get('calls', 0)} 次模型请求，收到 {usage.get('responses', 0)} 个有效 JSON 回复。"
                "请结合执行日志判断结果；单次通过不代表整体修复成功率。"
                if usage.get("calls", 0) else "已选择模型 API 模式，但本次尚未发起模型请求。请检查前置步骤。")
    else:
        note = "Agent 回复为手写预设，文件修改与 pytest 执行为真实运行。这验证工程流程，不代表真实模型的修复能力。"
    status = "修复验证通过" if success else "需要人工检查"
    events = []
    for index, event in enumerate(report["events"], 1):
        kind, _, attempt = event["stage"].partition(":")
        title = LABELS.get(kind, kind) + (f" · 第 {attempt} 轮" if attempt else "")
        passed = event["status"] == "passed"
        data = event.get("data")
        if isinstance(data, dict) and "log" in data:
            details = (f'<div class="testcounts">测试 {data.get("tests", 0)} · '
                       f'失败 {data.get("failed", 0)} · 错误 {data.get("errors", 0)} · '
                       f'跳过 {data.get("skipped", 0)}</div><pre>{escape(data["log"])}</pre>')
        else:
            details = f'<pre>{pretty(data)}</pre>' if data is not None else '<p>补丁已完成路径、匹配和语法检查。</p>'
        if event.get("error"):
            details += f'<p class="error">{escape(event["error"])}</p>'
        events.append(f'''<details class="event" {"open" if not passed else ""}>
<summary><span class="step-number">{index:02}</span><span class="step-title">{escape(title)}</span>
<span class="pill {"good" if passed else "bad"}">{"完成" if passed else "未通过"}</span>
<span class="duration">{event.get("duration", 0):.2f}s</span></summary>{details}</details>''')
    diff_lines = []
    for line in report.get("diff", "").splitlines():
        style = "add" if line.startswith("+") else "remove" if line.startswith("-") else "context"
        diff_lines.append(f'<span class="{style}">{escape(line)}</span>')
    diff = "".join(diff_lines) or "本次没有生成修改。"
    token_count = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    token_display = str(token_count) if not live or usage.get("usage_reported_calls", 0) else "未返回"
    last = report["attempts"][-1] if report["attempts"] else {}
    test_count = last.get("tests", {}).get("tests", "—")
    findings = last.get("review", {}).get("findings", [])
    review_html = "".join(f"<li>{escape(finding)}</li>" for finding in findings)
    if not review_html:
        review_html = "<li>未得到通过的审查结果，请检查执行记录。</li>"
    error = f'<div class="error-box">{escape(report["error"])}</div>' if report.get("error") else ""
    html = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BugFix Agent · 修复报告</title><link rel="icon" href="data:,"><style>
:root{{--bg:#f4f6fa;--ink:#17213a;--muted:#63708a;--line:#dce2ee;--blue:#3459d9;--green:#126d50}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Segoe UI","Microsoft YaHei",sans-serif}}
.topbar{{background:#14213e;color:white;padding:18px 6%;display:flex;align-items:center;justify-content:space-between;gap:16px}}
.brand{{font-size:20px;font-weight:750;letter-spacing:-.5px}}.brand b{{color:#9eb8ff}}.topbar small{{color:#b6c6e6}}
main{{max-width:1180px;margin:34px auto;padding:0 24px 48px}} .eyebrow{{text-transform:uppercase;letter-spacing:2px;font-size:12px;font-weight:700;color:var(--blue)}}
.hero{{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}}h1{{font-size:34px;letter-spacing:-1px;margin:8px 0 12px;line-height:1.3}}h2{{font-size:19px;margin:0 0 16px}}p{{margin:8px 0}}.muted{{color:var(--muted)}}
.badge{{display:inline-flex;padding:9px 14px;border:1px solid #bedccd;border-radius:8px;background:#e7f4ed;color:var(--green);font-weight:700;white-space:nowrap;margin-top:25px}}
.badge.failed{{background:#fff1ed;color:#9c3a24;border-color:#efc3b7}}
.notice{{margin:22px 0;padding:14px 18px;border-left:4px solid var(--blue);background:#eaf0ff;color:#35496e;border-radius:0 8px 8px 0}}
.metrics{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}}.metric,.panel{{background:white;border:1px solid var(--line);border-radius:12px}}
.metric{{padding:18px 22px}}.metric .label{{font-size:12px;color:var(--muted)}}.metric strong{{display:block;font-size:28px;line-height:1.5}}.metric small{{font-size:12px;color:var(--muted)}}
.columns{{display:grid;grid-template-columns:1.55fr 1fr;gap:22px;align-items:start}}.columns>div{{min-width:0}}.panel{{padding:24px;margin-bottom:22px;min-width:0}}.issue{{white-space:pre-wrap;overflow-wrap:anywhere}}
.event{{border:1px solid var(--line);border-radius:8px;margin:10px 0;overflow:hidden}}summary{{display:flex;align-items:center;gap:12px;padding:13px;cursor:pointer;list-style:none}}summary::-webkit-details-marker{{display:none}}
summary:hover{{background:#f6f8fd}}summary:focus-visible{{outline:2px solid var(--blue);outline-offset:-2px}}.step-number{{font-size:12px;font-family:monospace;color:#7584a5}}.step-title{{font-weight:600;flex:1}}.pill{{font-size:11px;padding:2px 8px;border-radius:12px;white-space:nowrap}}.good{{background:#e7f4ed;color:#126d50}}.bad{{background:#fff0ea;color:#a34029}}.duration{{font-size:12px;color:var(--muted);min-width:42px;text-align:right}}
pre{{margin:0;background:#111c33;color:#dce6fb;padding:18px;overflow:auto;font:12px/1.7 Consolas,"Cascadia Code",monospace;tab-size:4;max-height:520px}}.event p,.testcounts{{padding:0 16px 12px}}.testcounts{{font-size:12px;color:var(--muted)}}
.diff{{border-radius:8px;white-space:pre;max-height:650px}}.diff span{{display:block;min-height:20px}}.add{{color:#91e8b7;background:#183a35}}.remove{{color:#ffa6a8;background:#402735}}.context{{color:#c7d3ec}}
.links{{display:flex;flex-wrap:wrap;gap:10px;margin-top:20px}}a.button{{display:inline-block;padding:9px 14px;border:1px solid var(--line);border-radius:7px;background:white;color:var(--blue);font-weight:600;text-decoration:none;font-size:13px}}a.button:hover{{background:#eef3ff}}
ul{{padding-left:20px}}li{{margin-bottom:9px}}.error,.error-box{{color:#9b3325}}.error-box{{padding:14px;background:#fff0eb;border:1px solid #edc7bd;border-radius:8px;margin:18px 0}}
.footer{{font-size:12px;color:var(--muted);margin-top:28px;overflow-wrap:anywhere}}code{{font-family:Consolas,monospace}}.architecture{{font-size:13px;color:var(--muted);padding:12px 0;border-top:1px solid var(--line)}}
@media(max-width:800px){{.columns{{grid-template-columns:1fr}}.metrics{{grid-template-columns:repeat(2,1fr)}}.hero{{display:block}}h1{{font-size:27px}}.badge{{margin-top:0}}main{{padding:0 14px 30px}}.panel{{padding:18px}}.topbar{{padding:15px 18px}}.topbar small{{display:none}}}}
</style></head><body><header class="topbar"><div class="brand">BugFix<span> / </span><b>Agent</b></div><small>定位 → 复现 → 修复 → 验证 → 审查</small></header>
<main><div class="hero"><div><div class="eyebrow">Evidence-driven repair</div><h1>让每一次修复，都有验证依据。</h1><p class="muted">{escape(mode)}</p></div><div class="badge {"" if success else "failed"}">{status}</div></div>
<div class="notice">{note}</div>{error}
<section class="metrics"><div class="metric"><div class="label">修复轮数</div><strong>{len(report["attempts"])} <small>/ {report["max_attempts"]}</small></strong><small>有界重试，保留失败原因</small></div>
<div class="metric"><div class="label">最终执行测试</div><strong>{test_count}</strong><small>现有测试 + 新增回归测试</small></div>
<div class="metric"><div class="label">总耗时</div><strong>{report["duration"]:.1f}<small> 秒</small></strong><small>包含模型与测试执行</small></div>
<div class="metric"><div class="label">API 请求 / Tokens</div><strong>{usage.get("calls", 0)} <small>/ {token_display}</small></strong><small>{"仅累计接口已返回的 usage" if live else "预设演示没有 API 消耗"}</small></div></section>
<div class="columns"><div><section class="panel"><h2>问题描述</h2><p class="issue">{escape(report["issue"])}</p></section>
<section class="panel"><h2>执行证据</h2><p class="muted">点击步骤查看角色输出或真实测试日志。</p>{"".join(events)}</section></div>
<div><section class="panel"><h2>审查结论</h2><ul>{review_html}</ul><div class="architecture">同一模型的独立角色 + 显式状态机。模型提出修改，由工具验证结果。</div></section>
<section class="panel"><h2>代码变更</h2><pre class="diff">{diff}</pre><div class="links"><a class="button" href="patch.diff" download>下载补丁</a><a class="button" href="report.json" download>运行数据</a><a class="button" href="PR.md" download>PR 草稿</a></div></section></div></div>
<div class="footer">运行编号：{escape(report["id"])} · 模型：{escape(report["model"])}<br>输入仓库：{escape(report["source"])}<br>本项目只支持可信的小型 Python 仓库；工作副本不是安全沙箱。PR 草稿仅保存在本机。</div></main></body></html>'''
    (output / "report.html").write_text(html, encoding="utf-8")
    draft = f'''# Bug 修复草稿：{report['issue'].splitlines()[0][:90]}

## 问题
{report['issue']}

## 结果
- 状态：{status}
- 运行方式：{mode}
- 修复轮数：{len(report['attempts'])}
- 修复说明：{last.get('summary', '未生成有效修复')}
- 最终测试数：{test_count}
- 基线通过：{bool(report.get('baseline') and report['baseline']['passed'])}
- 原实现复现断言失败数：{(report.get('reproduction') or {}).get('assertion_failures', 0)}

## 审查
{chr(10).join('- ' + finding for finding in findings) or '- 尚未得到通过的审查结论'}

## 证据与限制
详见同目录 report.html、report.json、patch.diff。此文件为本地草稿，未创建远端 PR。
{note}
'''
    (output / "PR.md").write_text(draft, encoding="utf-8")
