from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json_dumps(value)
    return str(value)
