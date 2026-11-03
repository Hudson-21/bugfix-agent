from bugfix_agent.runner import run_tests


def test_pytest_results_distinguish_failures_from_errors(tmp_path):
    test = tmp_path / "test_sample.py"
    test.write_text("def test_value():\n    assert 2 == 3\n", encoding="utf-8")
    failed = run_tests(tmp_path, ["test_sample.py"], tmp_path / "logs")
    assert failed.failed == 1 and failed.assertion_failures == 1 and failed.errors == 0 and not failed.passed
    test.write_text("import module_that_does_not_exist_123\n", encoding="utf-8")
    error = run_tests(tmp_path, ["test_sample.py"], tmp_path / "logs")
    assert error.errors > 0 and not error.passed


def test_runtime_exception_is_not_an_assertion_failure(tmp_path):
    (tmp_path / "test_sample.py").write_text(
        "def test_value():\n    assert 1 / 0 == 1\n", encoding="utf-8")
    result = run_tests(tmp_path, ["test_sample.py"], tmp_path / "logs")
    assert result.failed == 1 and result.assertion_failures == 0


def test_tests_do_not_receive_api_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "private-test-key")
    (tmp_path / "test_sample.py").write_text(
        "import os\ndef test_secret():\n    assert 'DEEPSEEK_API_KEY' not in os.environ\n", encoding="utf-8")
    result = run_tests(tmp_path, ["test_sample.py"], tmp_path / "logs")
    assert result.passed and result.tests == 1


def test_timeout_cannot_be_success(tmp_path):
    (tmp_path / "test_sample.py").write_text(
        "import time\ndef test_wait():\n    time.sleep(20)\n", encoding="utf-8")
    result = run_tests(tmp_path, ["test_sample.py"], tmp_path / "logs", timeout=0.5)
    assert result.timed_out and not result.passed
