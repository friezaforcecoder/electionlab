from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


class OllamaProvider:
    def __init__(self, base_url: str, model: str, executable: str | None = None):
        self.base_url = base_url.rstrip("/")
        host = (urlparse(self.base_url).hostname or "").lower()
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("The Local AI provider only accepts loopback/localhost endpoints.")
        self.model = model
        self.executable = (executable or "").strip() or None

    def health(self, timeout: int = 5) -> dict:
        req = urllib.request.Request(f"{self.base_url}/api/tags", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            names = [m.get("name") or m.get("model") for m in data.get("models", [])]
            return {"reachable": True, "models": [n for n in names if n], "selected_available": self.model in names}
        except Exception as exc:
            return {"reachable": False, "models": [], "selected_available": False, "error": str(exc)}

    def _ollama_executable(self) -> str | None:
        if self.executable:
            candidate=os.path.expandvars(os.path.expanduser(self.executable))
            if os.path.isfile(candidate):
                return candidate
        exe = shutil.which("ollama")
        if exe:
            return exe
        if os.name == "nt":
            candidates = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Ollama\ollama.exe"),
                os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
                os.path.expandvars(r"%ProgramFiles%\Ollama\Ollama.exe"),
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\Ollama.exe"),
                os.path.expandvars(r"%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe"),
            ]
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    return candidate
        return None

    def find_executable(self) -> str | None:
        """Return the configured or auto-detected local Ollama executable, if any."""
        return self._ollama_executable()

    def ensure_running(self, wait_seconds: float = 8.0) -> dict:
        """Best-effort local-service startup.

        If Ollama is installed but the local server is not listening, ElectionLab starts
        ``ollama serve`` without opening a console window, then waits briefly. This only
        starts a localhost service; it never changes the configured endpoint to a remote host.
        """
        current = self.health(timeout=2)
        if current.get("reachable"):
            return {**current, "started": False}

        exe = self._ollama_executable()
        if not exe:
            return {
                **current,
                "started": False,
                "start_error": "Ollama is not running and ElectionLab could not find the Ollama executable.",
            }
        try:
            kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
                "stdin": subprocess.DEVNULL,
                "close_fds": True,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
            subprocess.Popen([exe, "serve"], **kwargs)
        except Exception as exc:
            return {**current, "started": False, "start_error": f"ElectionLab found Ollama but could not start it: {exc}"}

        deadline = time.monotonic() + max(1.0, wait_seconds)
        last = current
        while time.monotonic() < deadline:
            time.sleep(.4)
            last = self.health(timeout=2)
            if last.get("reachable"):
                return {**last, "started": True}
        return {
            **last,
            "started": False,
            "start_error": "ElectionLab started Ollama, but its local API did not become ready in time.",
        }

    def chat(self, prompt: str, system: str | None = None, timeout: int = 180, auto_start: bool = True) -> str:
        if auto_start:
            state = self.ensure_running()
            if not state.get("reachable"):
                details = state.get("start_error") or state.get("error") or "unknown local-service error"
                raise RuntimeError(f"Local AI is enabled, but Ollama is unavailable. {details}")
            if not state.get("selected_available"):
                models = ", ".join(state.get("models", [])[:8]) or "none"
                raise RuntimeError(f"Ollama is running, but model {self.model!r} is not installed. Installed models: {models}")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach local Ollama at {self.base_url}: {exc}") from exc
