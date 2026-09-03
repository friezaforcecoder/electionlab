from __future__ import annotations

import copy
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .settings import SettingsManager


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", s).strip("-")[:70] or "campaign"


class CampaignManager:
    def __init__(self, settings: SettingsManager):
        self.settings = settings
        self.root = settings.path_for("Campaigns")

    def create(self, title: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        campaign = {
            "schema_version": 6,
            "id": str(uuid.uuid4()),
            "title": title,
            "created_at": now,
            "updated_at": now,
            "parent_campaign_id": None,
            "branch_label": "Main Timeline",
            "timeline": [],
            "debates": [],
            **payload,
        }
        return self.save(campaign)

    def save(self, campaign: dict[str, Any]) -> dict[str, Any]:
        campaign["schema_version"] = max(6, int(campaign.get("schema_version", 1) or 1))
        campaign.setdefault("debates", [])
        campaign["updated_at"] = datetime.now(timezone.utc).isoformat()
        path = self.root / f"{_slug(campaign['title'])}__{campaign['id'][:8]}.elsave.json"
        old_path = Path(campaign.get("_path", "")) if campaign.get("_path") else None
        path.write_text(json.dumps(campaign, indent=2, ensure_ascii=False), encoding="utf-8")
        if old_path and old_path != path and old_path.exists():
            try:
                old_path.unlink()
            except OSError:
                pass
        campaign["_path"] = str(path)
        return campaign

    def list(self) -> list[dict[str, Any]]:
        out = []
        for path in sorted(self.root.glob("*.elsave.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data.setdefault("schema_version", 1)
                data.setdefault("debates", [])
                data["_path"] = str(path)
                out.append(data)
            except Exception:
                continue
        return out

    def delete(self, campaign: dict[str, Any]) -> bool:
        path_text = campaign.get("_path")
        if path_text:
            path = Path(path_text)
        else:
            matches = list(self.root.glob(f"*__{str(campaign.get('id',''))[:8]}.elsave.json"))
            path = matches[0] if matches else None
        if not path or not path.exists():
            return False
        path.unlink()
        return True

    def branch(self, campaign: dict[str, Any], label: str) -> dict[str, Any]:
        child = copy.deepcopy(campaign)
        child.pop("_path", None)
        parent_id = campaign["id"]
        child["id"] = str(uuid.uuid4())
        child["parent_campaign_id"] = parent_id
        child["branch_label"] = label or "Branch"
        child["title"] = f"{campaign['title']} — {child['branch_label']}"
        child["created_at"] = datetime.now(timezone.utc).isoformat()
        child.setdefault("debates", [])
        child["timeline"].append({
            "type": "branch_created",
            "at": child["created_at"],
            "from_campaign_id": parent_id,
            "label": child["branch_label"],
        })
        return self.save(child)
