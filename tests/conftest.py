import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def api():
    path = Path(__file__).resolve().parents[1] / "server" / "message_api.py"
    spec = importlib.util.spec_from_file_location("message_api_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

