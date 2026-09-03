from __future__ import annotations

import json
import platform
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionDiagnostics:
    """Single recurrent log for the most recent ElectionLab session.

    The file is overwritten at every launch so users always have one obvious log
    to share. It intentionally never logs API-key values or other secrets.
    """

    def __init__(self, logs_dir: Path, build: str):
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.path = logs_dir / "latest_session.log"
        self.build = build
        self._lock = threading.RLock()
        self._started = time.perf_counter()
        self._ui_action = "startup"
        self._last_ui_heartbeat = time.perf_counter()
        self.path.write_text("", encoding="utf-8")
        self.log("INFO", "SESSION_START", build=build, python=platform.python_version(), platform=platform.platform())

    @staticmethod
    def _safe(value: Any):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        try:
            return json.loads(json.dumps(value, default=str))
        except Exception:
            return str(value)

    def log(self, level: str, event: str, **fields: Any) -> None:
        now = datetime.now().astimezone().isoformat(timespec="milliseconds")
        elapsed = time.perf_counter() - self._started
        payload = {k: self._safe(v) for k, v in fields.items()}
        line = f"{now} +{elapsed:09.3f}s [{level.upper():7}] [{threading.current_thread().name}] {event}"
        if payload:
            line += " " + json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._lock:
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    def exception(self, event: str, exc: BaseException, **fields: Any) -> None:
        fields = dict(fields)
        fields["error"] = str(exc)
        fields["traceback"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.log("ERROR", event, **fields)

    @contextmanager
    def span(self, event: str, **fields: Any):
        started = time.perf_counter()
        self.log("DEBUG", event + "_BEGIN", **fields)
        try:
            yield
        except Exception as exc:
            self.exception(event + "_FAILED", exc, duration_ms=round((time.perf_counter() - started) * 1000, 1), **fields)
            raise
        else:
            self.log("DEBUG", event + "_END", duration_ms=round((time.perf_counter() - started) * 1000, 1), **fields)

    def set_ui_action(self, action: str) -> None:
        self._ui_action = action or "idle"
        self.log("DEBUG", "UI_ACTION", action=self._ui_action)

    def clear_ui_action(self, expected: str | None = None) -> None:
        if expected is None or self._ui_action == expected:
            self._ui_action = "idle"

    def ui_heartbeat(self, stall_threshold_s: float = 1.25) -> None:
        now = time.perf_counter()
        gap = now - self._last_ui_heartbeat
        self._last_ui_heartbeat = now
        if gap >= stall_threshold_s:
            self.log("WARNING", "UI_STALL_DETECTED", gap_seconds=round(gap, 3), current_action=self._ui_action)

    def log_settings_snapshot(self, settings: Any) -> None:
        # Deliberately omit API keys; SettingsManager does not hold their values anyway.
        self.log(
            "INFO", "SETTINGS_SNAPSHOT",
            data_root=str(getattr(settings, "data_root", "")),
            offline_lock=bool(getattr(settings, "offline_lock", False)),
            internet_research=bool(getattr(settings, "internet_research", False)),
            openai_enabled=bool(getattr(settings, "openai_enabled", False)),
            local_ai_enabled=bool(getattr(settings, "local_ai_enabled", False)),
            openai_model=str(getattr(settings, "openai_model", "")),
            ollama_model=str(getattr(settings, "ollama_model", "")),
            ollama_base_url=str(getattr(settings, "ollama_base_url", "")),
        )

    def close(self) -> None:
        self.log("INFO", "SESSION_END")
