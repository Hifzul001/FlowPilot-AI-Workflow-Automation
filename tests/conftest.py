from pathlib import Path
import tempfile

import pytest

from app.config import WORKFLOW_CONFIG
from app.engine import WorkflowEngine
from app.loader import WorkflowLoader
from app.llm import GeminiService
from app.tools import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_path():
    with tempfile.TemporaryDirectory(prefix="flowpilot-test-", dir=ROOT) as folder:
        yield Path(folder)


class DisabledLLM(GeminiService):
    def __init__(self):
        super().__init__(api_key=None)

    @property
    def enabled(self):
        return False


@pytest.fixture
def workflows():
    return WorkflowLoader(WORKFLOW_CONFIG).load()


@pytest.fixture
def engine(workflows):
    return WorkflowEngine(workflows, ToolRegistry(DisabledLLM()))


@pytest.fixture
def sample_dir():
    return Path(__file__).resolve().parents[1] / "data" / "samples"
