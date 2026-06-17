"""테스트 fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def load_fixture():
    """fixture 파일을 로드하는 헬퍼."""

    def _load(name: str) -> dict[str, Any]:
        path = Path(__file__).parent / "fixtures" / name
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    return _load
