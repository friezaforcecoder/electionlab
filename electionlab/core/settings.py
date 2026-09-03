from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from .model_ids import OPENAI_DEFAULT_MODEL, normalize_openai_model

APP_DIR = Path(__file__).resolve().parents[2]
PORTABLE_CONFIG = APP_DIR / "portable_config.json"


@dataclass
class AppSettings:
    data_root: str = str(APP_DIR / "ElectionLabData")
    offline_lock: bool = False
    internet_research: bool = True
    openai_enabled: bool = False
    local_ai_enabled: bool = True
    openai_model: str = OPENAI_DEFAULT_MODEL
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:12b"
    ollama_executable: str = ""
    default_mode: str = "Analytical 2"
    monte_carlo_runs: int = 3000
    campaign_history_provider: str = "Deterministic local"

    @property
    def root(self) -> Path:
        return Path(os.path.expandvars(os.path.expanduser(self.data_root))).resolve()


class SettingsManager:
    def __init__(self, path: Path = PORTABLE_CONFIG):
        self.path = path
        self.settings = self.load()
        self.ensure_layout()

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            raw["openai_model"] = normalize_openai_model(raw.get("openai_model"))
            allowed = {f.name for f in AppSettings.__dataclass_fields__.values()}
            return AppSettings(**{k: v for k, v in raw.items() if k in allowed})
        except Exception:
            return AppSettings()

    def save(self) -> None:
        self.path.write_text(json.dumps(asdict(self.settings), indent=2), encoding="utf-8")
        self.ensure_layout()

    def update(self, **kwargs: Any) -> None:
        if "openai_model" in kwargs:
            kwargs["openai_model"] = normalize_openai_model(kwargs.get("openai_model"))
        for k, v in kwargs.items():
            if hasattr(self.settings, k):
                setattr(self.settings, k, v)
        self.save()

    def ensure_layout(self) -> None:
        root = self.settings.root
        for rel in [
            "KnowledgeVault/profiles",
            "KnowledgeVault/photos",
            "Campaigns",
            "Saves",
            "ResearchCache",
            "Models",
            "DataPacks",
            "Extensions",
            "Exports",
            "Logs",
        ]:
            (root / rel).mkdir(parents=True, exist_ok=True)

    def path_for(self, rel: str) -> Path:
        self.ensure_layout()
        return self.settings.root / rel
