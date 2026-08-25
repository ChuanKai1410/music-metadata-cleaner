from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
TEST_WORKSPACE_ROOT = PROJECT_ROOT / ".test-workspaces"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


@pytest.fixture
def tmp_path() -> Path:
    """Project-local temp path that avoids locked Windows temp directories."""

    TEST_WORKSPACE_ROOT.mkdir(exist_ok=True)
    path = TEST_WORKSPACE_ROOT / uuid.uuid4().hex
    path.mkdir()
    return path
