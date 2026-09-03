from __future__ import annotations

import json
import re
import ssl
import urllib.parse
import urllib.request
import time
from pathlib import Path

try:
    import certifi
except Exception:  # pragma: no cover - installer includes it
    certifi = None

from electionlab.core.database import KnowledgeVault
from electionlab.core.settings import SettingsManager


class PhotoService:
    """Fetch and cache optional public profile portraits from Wikipedia/Wikimedia.

    0.7 improves ambiguous-name handling. Instead of blindly accepting Wikipedia's first
    search hit, ElectionLab uses the saved profile's career/background as a disambiguation
    hint and scores several candidate pages. A failure for one person never aborts the batch.
    """

    USER_AGENT = "ElectionLab/0.11.1 (local political simulation app; portrait cache)"

    def __init__(self, settings: SettingsManager, vault: KnowledgeVault):
        self.settings = settings
        self.vault = vault
        self.root = settings.path_for("KnowledgeVault/photos")
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _slug(name: str) -> str:
        text = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
        return text[:80] or "portrait"

    @staticmethod
    def _ssl_context() -> ssl.SSLContext:
        if certifi:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    def _career_hint(self, name: str) -> str:
        p = self.vault.get_profile(name) or {}
        career = str(p.get("career") or "").lower()
        profile_type = str(p.get("profile_type") or "")
        if "president" in career or profile_type == "historical_political":
            return "president"
        # Wikipedia search benefits from compact identity words more than a long biography.
        mappings = [
            ("musician", "musician"), ("rapper", "rapper"), ("actor", "actor"),
            ("athlete", "athlete"), ("online creator", "YouTuber"),
            ("podcaster", "podcaster"), ("comedian", "comedian"),
            ("chef", "chef"), ("business", "businessperson"),
            ("science", "scientist"), ("tv", "television"),
        ]
        for token, hint in mappings:
            if token in career:
                return hint
        return ""

    def _query_pages(self, search: str) -> list[dict]:
        params = urllib.parse.urlencode({
            "action": "query",
            "generator": "search",
            "gsrsearch": search,
            "gsrnamespace": 0,
            "gsrlimit": 8,
            "prop": "pageimages|info|pageprops",
            "piprop": "thumbnail|original",
            "pithumbsize": 720,
            "inprop": "url",
            "format": "json",
            "formatversion": 2,
        })
        req = urllib.request.Request(
            f"https://en.wikipedia.org/w/api.php?{params}",
            headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"},
        )
        last_error = None
        for attempt in range(1, 3):
            try:
                with urllib.request.urlopen(req, timeout=25, context=self._ssl_context()) as resp:
                    return json.loads(resp.read().decode("utf-8")).get("query", {}).get("pages", [])
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * attempt)
        raise last_error or RuntimeError("Wikipedia portrait lookup failed.")

    @staticmethod
    def _score_page(name: str, hint: str, page: dict) -> float:
        title = str(page.get("title") or "").strip()
        tl, nl, hl = title.lower(), name.lower().strip(), hint.lower().strip()
        score = 0.0
        if tl == nl:
            score += 120
        elif tl.startswith(nl + " ("):
            score += 105
        elif tl.startswith(nl):
            score += 85
        elif nl in tl:
            score += 55
        # Prefer pages with actual portrait-capable media.
        if page.get("thumbnail") or page.get("original"):
            score += 35
        else:
            score -= 80
        if hl and hl in tl:
            score += 25
        # Common disambiguation/list pages are poor portrait sources.
        if "disambiguation" in tl or tl.startswith("list of"):
            score -= 100
        return score

    def _best_page(self, name: str) -> dict:
        hint = self._career_hint(name)
        queries = []
        if hint:
            queries.extend([f'"{name}" {hint}', f'intitle:"{name}" {hint}'])
        queries.extend([f'intitle:"{name}"', name])

        candidates: dict[int, dict] = {}
        last_error = None
        for query in queries:
            try:
                for page in self._query_pages(query):
                    pid = int(page.get("pageid") or hash(page.get("title")))
                    candidates[pid] = page
            except ssl.SSLCertVerificationError as exc:
                raise RuntimeError(
                    "Verified HTTPS failed while contacting Wikipedia. ElectionLab kept certificate "
                    "verification enabled. Re-run the installer/update so the current CA bundle is installed. "
                    f"Technical detail: {exc}"
                ) from exc
            except Exception as exc:
                last_error = exc
                continue
            # If the first targeted query found a very strong page, avoid extra network work.
            if candidates:
                best = max(candidates.values(), key=lambda p: self._score_page(name, hint, p))
                if self._score_page(name, hint, best) >= 130:
                    return best

        if not candidates:
            if last_error:
                raise RuntimeError(f"Could not look up a portrait for {name}: {last_error}") from last_error
            raise RuntimeError(f"No Wikipedia page was found for {name}.")
        return max(candidates.values(), key=lambda p: self._score_page(name, hint, p))


    def _wikidata_image_url(self, page: dict) -> str | None:
        """Best-effort portrait fallback using the selected page's Wikidata P18 image.

        Some Wikipedia pages expose no pageimage even though their linked Wikidata
        entity has a Commons portrait. This keeps ambiguous-name resolution anchored
        to the already-selected page instead of launching a broad image search.
        """
        qid = ((page.get("pageprops") or {}).get("wikibase_item") or "").strip()
        if not qid:
            return None
        url = f"https://www.wikidata.org/wiki/Special:EntityData/{urllib.parse.quote(qid)}.json"
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT, "Accept": "application/json"})
        last_error = None
        for attempt in range(1, 3):
            try:
                with urllib.request.urlopen(req, timeout=25, context=self._ssl_context()) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                claims = (((data.get("entities") or {}).get(qid) or {}).get("claims") or {}).get("P18") or []
                if not claims:
                    return None
                filename = (((claims[0].get("mainsnak") or {}).get("datavalue") or {}).get("value") or "").strip()
                if not filename:
                    return None
                return "https://commons.wikimedia.org/wiki/Special:Redirect/file/" + urllib.parse.quote(filename) + "?width=900"
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.8 * attempt)
        return None

    def _download_blob(self, url: str, name: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
        last_error = None
        # A slow Wikimedia response should not cause Fetch All to permanently
        # abandon an otherwise resolvable person. 0.10 intentionally gives each
        # image more room than earlier builds and retries transient failures.
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(req, timeout=50, context=self._ssl_context()) as resp:
                    return resp.read(8 * 1024 * 1024 + 1)
            except Exception as exc:
                last_error = exc
                if attempt < 3:
                    time.sleep(1.2 * attempt)
        raise RuntimeError(f"Portrait download failed for {name} after 3 attempts: {last_error}") from last_error

    def fetch_and_cache(self, name: str) -> str:
        s = self.settings.settings
        if s.offline_lock:
            raise RuntimeError("Offline Lock is enabled. Portrait download is blocked.")
        if not s.internet_research:
            raise RuntimeError("Internet Research is disabled in Settings.")

        page = self._best_page(name)
        image_url = (page.get("thumbnail") or {}).get("source") or (page.get("original") or {}).get("source")
        if not image_url:
            image_url = self._wikidata_image_url(page)
        if not image_url:
            raise RuntimeError(
                f"Wikipedia found '{page.get('title', name)}' for {name}, but neither the page nor its linked Wikidata record provided a usable portrait image."
            )

        suffix = Path(urllib.parse.urlparse(image_url).path).suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            suffix = ".jpg"
        out = self.root / f"{self._slug(name)}{suffix}"
        blob = self._download_blob(image_url, name)
        if len(blob) > 8 * 1024 * 1024:
            raise RuntimeError("Portrait file was unexpectedly large; download was cancelled.")
        out.write_bytes(blob)
        source_url = page.get("fullurl") or image_url
        self.vault.update_photo(name, str(out), source_url)
        return str(out)

    def import_local(self, name: str, source_path: str) -> str:
        src = Path(source_path)
        if not src.exists() or not src.is_file():
            raise RuntimeError("The selected portrait file does not exist.")
        suffix = src.suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
            raise RuntimeError("Choose a JPG, PNG, or WEBP image.")
        out = self.root / f"{self._slug(name)}{suffix}"
        blob = src.read_bytes()
        if len(blob) > 8 * 1024 * 1024:
            raise RuntimeError("Portrait file is larger than 8 MB.")
        out.write_bytes(blob)
        self.vault.update_photo(name, str(out), f"local-file:{src.name}")
        return str(out)
