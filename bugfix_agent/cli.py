"""CLI entry point for demo and live DeepSeek repair."""

import argparse
import getpass
from datetime import datetime
import json
from pathlib import Path
import sys
import uuid
import webbrowser
import warnings

from bugfix_agent.engine import run
from bugfix_agent.provider import DeepSeekProvider, ReplayProvider
from bugfix_agent.report import LABELS


CASES = Path(__file__).parent / "cases"


def progress(event):
    kind, _, attempt = event["stage"].partition(":")
    title = LABELS.get(kind, kind) + (f" #{attempt}" if attempt else "")
    state = {"running": "执行中", "passed": "完成", "failed": "失败"}[event["status"]]
    print(f"  [{state}] {title}", flush=True)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="BugFix Agent — DeepSeek 多角色 Python Bug 修复助手")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="内置案例；默认预设响应演示，不调用模型")
    demo.add_argument("--case", choices=["coupon", "pagination", "average", "inventory"], default="coupon")
    demo.add_argument("--live", action="store_true", help="对此内置案例调用配置的模型 API")
    custom = commands.add_parser("run", help="调用 DeepSeek 修复可信的小型 Python 仓库")
    custom.add_argument("--repo", type=Path, required=True)
    custom.add_argument("--issue", required=True, help="实际行为、期望行为和复现输入")
    for subparser in (demo, custom):
        subparser.add_argument("--ask-key", action="store_true", help="隐藏输入本次 API 密钥，不保存到文件或环境变量")
        subparser.add_argument("--output", type=Path, help="新的输出目录，不能与输入仓库互相包含")
        subparser.add_argument("--max-attempts", type=int, choices=[1, 2], default=2)
        subparser.add_argument("--open", action="store_true", help="完成后用默认浏览器打开报告")
    args = parser.parse_args(argv)
    try:
        api_key = None
        if args.ask_key and (args.command == "run" or args.live):
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                api_key = getpass.getpass("API Key (hidden): ").strip()
            if not api_key:
                raise ValueError("密钥不能为空。")
        if args.command == "demo":
            case = CASES / args.case
            source = case / "repo"
            issue = json.loads((case / "issue.json").read_text(encoding="utf-8"))["issue"]
            provider = DeepSeekProvider(api_key=api_key) if args.live else ReplayProvider(case / "replay.json")
        else:
            source, issue = args.repo, args.issue
            provider = DeepSeekProvider(api_key=api_key)
        output_parent = Path.cwd() / "runs"
        if output_parent.resolve().is_relative_to(source.resolve()):
            output_parent = source.resolve().parent / "bugfix-agent-runs"
        output = args.output or (output_parent / (
            datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]))
        print("BugFix Agent | " + ("模型 API 运行" if provider.mode == "live" else "预设响应演示（非模型评测）"))
        if provider.mode == "live":
            print(f"接口：{provider.url}\n模型：{provider.model}")
        report = run(source, issue, provider, output, max_attempts=args.max_attempts, on_event=progress)
        html = output.resolve() / "report.html"
        print(f"\n结果：{report['status']}\n报告：{html}\n数据：{output.resolve() / 'report.json'}")
        if report.get("error"):
            print(f"原因：{report['error']}")
        if args.open:
            webbrowser.open(html.as_uri())
        return 0 if report["status"] == "success" else 1
    except (ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except (EOFError, getpass.GetPassWarning):
        print("无法隐藏输入密钥，请在交互终端运行 --ask-key，或设置 DEEPSEEK_API_KEY 环境变量。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
