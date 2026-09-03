from __future__ import annotations

import json
import ssl
import urllib.parse
import urllib.request
import time
from datetime import date
from typing import Any

try:
    import certifi
except Exception:  # pragma: no cover
    certifi = None


class WikipediaProfileProvider:
    """Small no-key web fallback used with local AI or as a basic cache source."""

    USER_AGENT = "ElectionLab/0.11 (local political simulation app)"

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        if certifi:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    def fetch_summary(self, name: str) -> dict[str, Any]:
        q = urllib.parse.urlencode({
            "action": "query", "generator": "search", "gsrsearch": name, "gsrlimit": 1,
            "prop": "extracts|info", "exintro": 1, "explaintext": 1, "inprop": "url",
            "format": "json", "formatversion": 2,
        })
        req = urllib.request.Request(f"https://en.wikipedia.org/w/api.php?{q}", headers={"User-Agent": self.USER_AGENT})
        last_error = None
        data = None
        for attempt in range(1, 3):
            try:
                with urllib.request.urlopen(req, timeout=30, context=self._ssl_context()) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(1.0)
        if data is None:
            raise RuntimeError(f"Web profile lookup failed after 2 attempts: {last_error}") from last_error
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            raise RuntimeError(f"No public reference page was found for {name}.")
        page = pages[0]
        return {
            "title": page.get("title") or name,
            "summary": (page.get("extract") or "")[:12000],
            "url": page.get("fullurl") or "https://en.wikipedia.org/",
        }

    def basic_profile(self, name: str) -> dict[str, Any]:
        ref = self.fetch_summary(name)
        return {
            "canonical_name": ref["title"],
            "profile_type": "public_figure",
            "source_type": "web_reference",
            "party": None,
            "home_state": None,
            "birth_year": None,
            "career": ref["summary"][:500] or None,
            "ideology": 0,
            "national_appeal": 0,
            "charisma": 50,
            "debate_skill": 50,
            "experience": 50,
            "name_recognition": 50,
            "known_positions": {},
            "inferred_positions": {},
            "controversies": [],
            "sources": [{"title": ref["title"], "url": ref["url"], "what_it_supports": "Basic identity/background only"}],
            "confidence": 0.45,
            "profile_status": "web_basic",
            "snapshot_date": date.today().isoformat(),
        }
