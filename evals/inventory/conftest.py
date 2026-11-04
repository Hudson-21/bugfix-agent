"""Load only the explicitly selected trusted repair workspace."""

import importlib.util
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption("--inventory-workspace", help="Directory containing inventory.py to evaluate")


@pytest.fixture
def reserve(request):
    selected = request.config.getoption("--inventory-workspace")
    if not selected:
        raise pytest.UsageError("Pass --inventory-workspace pointing to a trusted repair workspace")
    source = Path(selected).resolve() / "inventory.py"
    if not source.is_file():
        raise pytest.UsageError(f"inventory.py not found: {source}")
    spec = importlib.util.spec_from_file_location("inventory_under_evaluation", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.reserve
