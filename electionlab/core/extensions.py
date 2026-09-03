from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .settings import SettingsManager


@dataclass
class ExtensionInfo:
    id: str
    name: str
    version: str
    kind: str
    path: Path
    enabled: bool
    manifest: dict[str, Any]


class ExtensionManager:
    """Data-first extension framework.

    pre-1.0 build 0.2 intentionally supports manifests/data packs only. Executable third-party code is
    not auto-loaded yet; this leaves a future extension surface without creating an unsafe
    plugin execution path prematurely.
    """

    def __init__(self, settings: SettingsManager):
        self.settings = settings

    def discover(self) -> list[ExtensionInfo]:
        root = self.settings.path_for("Extensions")
        found: list[ExtensionInfo] = []
        for manifest_path in root.glob("*/manifest.json"):
            try:
                m = json.loads(manifest_path.read_text(encoding="utf-8"))
                found.append(
                    ExtensionInfo(
                        id=m.get("id", manifest_path.parent.name),
                        name=m.get("name", manifest_path.parent.name),
                        version=m.get("version", "0.0.0"),
                        kind=m.get("kind", "data_pack"),
                        path=manifest_path.parent,
                        enabled=bool(m.get("enabled", True)),
                        manifest=m,
                    )
                )
            except Exception:
                continue
        return found
