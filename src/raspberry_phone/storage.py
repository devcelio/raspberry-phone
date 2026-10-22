from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_json(path: Path, payload: object) -> None:
    """Write JSON beside its destination, then atomically replace it."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
