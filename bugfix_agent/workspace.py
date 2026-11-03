"""Small Python-only working copies and validated, atomic model patches."""

import ast
import difflib
import os
from pathlib import Path, PurePosixPath, PureWindowsPath


EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", "runs", "build", "dist"}
REGRESSION = "test_agent_regression.py"


def is_test(path: str) -> bool:
    p = PurePosixPath(path)
    return ("tests" in p.parts or "test" in p.parts or p.name.startswith("test_")
            or p.name.endswith("_test.py") or p.name == "conftest.py")


def python_files(root: Path):
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith(".")
                         and not (Path(directory) / d).is_symlink()
                         and not getattr(Path(directory) / d, "is_junction", lambda: False)())
        for name in sorted(files):
            path = Path(directory) / name
            if name.endswith(".py") and not name.startswith(".") and not path.is_symlink():
                yield path


class Workspace:
    def __init__(self, source: Path, output: Path):
        self.source = Path(source).resolve()
        self.output = Path(output).resolve()
        if not self.source.is_dir():
            raise ValueError("输入仓库不存在。")
        if self.output.is_relative_to(self.source) or self.source.is_relative_to(self.output):
            raise ValueError("运行输出目录与输入仓库不能互相包含。")
        self.root = self.output / "workspace"
        if self.root.exists():
            raise ValueError("工作副本已存在，请使用新的运行目录。")
        self.original = {}
        self.raw_original = {}
        total = 0
        for path in python_files(self.source):
            size = path.stat().st_size
            total += size
            if size > 100_000 or total > 500_000 or len(self.original) >= 80:
                raise ValueError("MVP 仅支持最多 80 个 Python 文件、总计 500 KB 的小仓库。")
            relative = path.relative_to(self.source).as_posix()
            self.original[relative] = path.read_text(encoding="utf-8-sig")
            self.raw_original[relative] = path.read_bytes().decode("utf-8-sig")
        if not self.original:
            raise ValueError("仓库中没有可读取的 Python 文件。")
        if REGRESSION in self.original:
            raise ValueError(f"仓库已占用保留文件名 {REGRESSION}。")
        self.expected = dict(self.original)
        self.root.mkdir(parents=True)
        for name, content in self.original.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def validate_path(self, path: str) -> str:
        if not isinstance(path, str) or not path or "\\" in path:
            raise ValueError("文件路径必须使用相对路径和正斜线。")
        parsed = PurePosixPath(path)
        if (parsed.is_absolute() or PureWindowsPath(path).drive or ".." in parsed.parts
                or ":" in path or any(part.startswith(".") for part in parsed.parts)
                or parsed.suffix != ".py" or path != parsed.as_posix()):
            raise ValueError(f"不允许的文件路径：{path}")
        target = (self.root / path).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("路径越过工作目录。")
        return path

    def inventory(self) -> dict:
        result = {}
        for name, content in self.expected.items():
            if is_test(name):
                continue
            try:
                tree = ast.parse(content)
                symbols = []
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        symbols.append(f"L{node.lineno} {node.name}({ast.unparse(node.args)})")
                    elif isinstance(node, ast.ClassDef):
                        symbols.append(f"L{node.lineno} class {node.name}")
                result[name] = "; ".join(symbols) or "module-level code"
            except SyntaxError as exc:
                raise ValueError(f"源文件语法错误：{name}:{exc.lineno}") from exc
        return result

    def read_sources(self, paths: list[str]) -> dict:
        if not isinstance(paths, list) or not 1 <= len(paths) <= 3:
            raise ValueError("Locator 必须选择 1 至 3 个源文件。")
        result = {}
        for path in paths:
            self.validate_path(path)
            if path not in self.expected or is_test(path):
                raise ValueError(f"不是可编辑源文件：{path}")
            result[path] = self.expected[path]
        return result

    def tests(self) -> dict:
        return {name: content for name, content in self.original.items() if is_test(name)}

    def add_regression(self, content: str):
        if not isinstance(content, str) or not 1 <= len(content) <= 20_000:
            raise ValueError("回归测试内容为空或过长。")
        try:
            tree = ast.parse(content)
        except SyntaxError as exc:
            raise ValueError("生成的回归测试不是合法 Python。") from exc
        tests = [node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]
        if not tests or not any(isinstance(n, ast.Assert) for test in tests for n in ast.walk(test)):
            raise ValueError("回归测试必须包含 test_ 函数和 assert 断言。")
        (self.root / REGRESSION).write_text(content, encoding="utf-8")
        self.expected[REGRESSION] = content

    def apply_edits(self, edits: list[dict], allowed: list[str]):
        if not isinstance(edits, list) or not 1 <= len(edits) <= 12:
            raise ValueError("补丁必须包含 1 至 12 个编辑。")
        pending = {}
        for edit in edits:
            if not isinstance(edit, dict):
                raise ValueError("编辑必须是 JSON 对象。")
            name = self.validate_path(edit.get("path"))
            if name not in allowed or name not in self.original or is_test(name):
                raise ValueError(f"禁止修改测试或未授权文件：{name}")
            search, replacement = edit.get("search"), edit.get("replace")
            if not isinstance(search, str) or not search or not isinstance(replacement, str):
                raise ValueError("search 必须为非空字符串，replace 必须为字符串。")
            content = pending.get(name, self.expected[name])
            if content.count(search) != 1:
                raise ValueError(f"{name} 中 search 必须精确匹配一次。")
            updated = content.replace(search, replacement, 1)
            if len(updated) > 100_000:
                raise ValueError("修改后的文件过大。")
            try:
                ast.parse(updated)
            except SyntaxError as exc:
                raise ValueError(f"补丁引入语法错误：{name}:{exc.lineno}") from exc
            pending[name] = updated
        if all(content == self.expected[name] for name, content in pending.items()):
            raise ValueError("补丁没有实际修改。")
        for name, content in pending.items():
            (self.root / name).write_text(content, encoding="utf-8")
            self.expected[name] = content

    def check_integrity(self):
        actual = {p.relative_to(self.root).as_posix(): p.read_text(encoding="utf-8")
                  for p in python_files(self.root)}
        if actual != self.expected:
            raise ValueError("测试执行修改了受保护的 Python 文件，运行已终止。")

    def diff(self) -> str:
        chunks = []
        for name, content in sorted(self.expected.items()):
            if self.original.get(name, "") != content:
                before = self.raw_original.get(name, "")
                after = content.replace("\n", "\r\n") if "\r\n" in before else content
                lines = difflib.unified_diff(
                    before.splitlines(keepends=True), after.splitlines(keepends=True),
                    fromfile=f"a/{name}" if name in self.original else "/dev/null", tofile=f"b/{name}")
                for line in lines:
                    chunks.append(line)
                    if not line.endswith("\n"):
                        chunks.append("\n\\ No newline at end of file\n")
        return "".join(chunks)
