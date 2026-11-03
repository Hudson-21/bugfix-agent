"""Fixed pytest execution; working-copy isolation is NOT a security sandbox."""

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET


@dataclass
class TestResult:
    returncode: int
    tests: int = 0
    failed: int = 0
    assertion_failures: int = 0
    errors: int = 0
    skipped: int = 0
    timed_out: bool = False
    duration: float = 0
    log: str = ""

    @property
    def passed(self) -> bool:
        return (self.returncode == 0 and self.tests > 0 and not self.timed_out
                and self.failed == 0 and self.errors == 0 and self.skipped == 0)

    def to_dict(self):
        return {**asdict(self), "passed": self.passed}


def run_tests(root: Path, targets: list[str], result_dir: Path, timeout: float = 30) -> TestResult:
    root, result_dir = Path(root).resolve(), Path(result_dir).resolve()
    result_dir.mkdir(parents=True, exist_ok=True)
    xml_path = result_dir / f"pytest-{uuid.uuid4().hex}.xml"
    config = result_dir / "pytest-empty.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT",
        "USERPROFILE", "LOCALAPPDATA", "APPDATA", "HOME", "LANG", "LC_ALL",
    }}
    env.update(PYTHONPATH=str(root), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    command = [sys.executable, "-m", "pytest", "-q", "--tb=short", "--assert=plain", "-c", str(config),
               "--rootdir", str(root), "--confcutdir", str(root), "-p", "no:cacheprovider",
               f"--junitxml={xml_path}", *targets]
    started = time.monotonic()
    proc = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            start_new_session=os.name != "nt")
    timed_out = False
    try:
        log, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True, timeout=10, check=False)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.kill()
        log, _ = proc.communicate(timeout=5)
        log += "\n测试执行超时；进程已终止。"
    result = TestResult(returncode=proc.returncode, timed_out=timed_out,
                        duration=round(time.monotonic() - started, 3), log=log[-60_000:])
    if xml_path.exists():
        try:
            cases = ET.parse(xml_path).getroot().findall(".//testcase")
            result.tests = len(cases)
            result.failed = sum(case.find("failure") is not None for case in cases)
            result.assertion_failures = sum(
                failure.get("message", "").startswith("AssertionError")
                for case in cases for failure in case.findall("failure"))
            result.errors = sum(case.find("error") is not None for case in cases)
            result.skipped = sum(case.find("skipped") is not None for case in cases)
        except ET.ParseError:
            result.errors += 1
    elif not timed_out:
        result.errors += 1
    return result
