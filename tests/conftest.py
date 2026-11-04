import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import AppPaths  # noqa: E402


@pytest.fixture
def paths(tmp_path: Path) -> AppPaths:
    p = AppPaths(data=tmp_path / "data", cache=tmp_path / "cache", logs=tmp_path / "logs")
    p.ensure()
    return p
