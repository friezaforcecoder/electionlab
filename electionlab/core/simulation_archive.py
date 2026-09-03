from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import SettingsManager


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-")[:80] or "simulation"


class SimulationArchive:
    """Portable saved instant-election results.

    Saved result files are plain JSON and live under the user's selected data root,
    so they remain portable and do not depend on the application install folder.
    """

    def __init__(self, settings: SettingsManager):
        self.settings = settings
        self.root = settings.path_for("Saves/Simulations")
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, result: dict[str, Any], label: str | None = None) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        a = (result.get("ticket_a") or {}).get("display_name") or "Ticket A"
        b = (result.get("ticket_b") or {}).get("display_name") or "Ticket B"
        title = (label or f"{a} vs {b}").strip()
        payload = {
            "schema_version": 1,
            "id": str(uuid.uuid4()),
            "title": title,
            "saved_at": now,
            "result": result,
        }
        path = self.root / f"{_slug(title)}__{payload['id'][:8]}.elsim.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        payload["_path"] = str(path)
        return payload

    def list(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.root.glob("*.elsim.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["_path"] = str(path)
                out.append(data)
            except Exception:
                continue
        return out

    def delete(self, item: dict[str, Any]) -> bool:
        path = Path(item.get("_path", "")) if item.get("_path") else None
        if not path or not path.exists():
            return False
        path.unlink()
        return True

    def export_result(self, result: dict[str, Any], path: str | Path) -> Path:
        out = Path(path)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        return out
