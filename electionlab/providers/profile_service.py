from __future__ import annotations

import json
from datetime import date
from typing import Any

from electionlab.core.database import KnowledgeVault
from electionlab.core.settings import SettingsManager
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIResearchProvider
from .photo_service import PhotoService
from .web_profile_provider import WikipediaProfileProvider


class ProfileService:
    def __init__(self, settings: SettingsManager, vault: KnowledgeVault, diagnostics=None):
        self.settings = settings
        self.vault = vault
        self.diagnostics = diagnostics
        self.photos = PhotoService(settings, vault)

    def _log(self, level: str, event: str, **fields):
        if self.diagnostics:
            self.diagnostics.log(level, event, **fields)

    def research_and_cache(self, name: str, progress=None) -> dict[str, Any]:
        """Research a public person using the best enabled provider path.

        Priority:
        1. OpenAI + web search when enabled.
        2. Public web reference + local Ollama structuring when local AI is enabled.
        3. Conservative web-only identity/background profile.

        All paths cache locally. Portrait fetch is best-effort and never makes profile research fail.
        """
        s = self.settings.settings
        def stage(percent: int, message: str, event: str = "PROFILE_RESEARCH_STAGE"):
            if progress:
                try: progress(int(percent), str(message))
                except TypeError: progress(str(message))
            self._log("DEBUG", event, name=name, percent=int(percent), message=str(message))
        stage(3, "Validating research settings…")
        if s.offline_lock:
            raise RuntimeError("Offline Lock is enabled. Remote research is blocked.")
        if not s.internet_research:
            raise RuntimeError("Internet Research is disabled in Settings.")

        profile = None
        openai_error = None
        local_error = None
        if s.openai_enabled:
            try:
                stage(12, "Searching public sources with OpenAI…")
                self._log("INFO", "PROFILE_RESEARCH_PROVIDER_BEGIN", name=name, provider="openai_web")
                provider = OpenAIResearchProvider(s.openai_model)
                profile = provider.research_person(name, use_web=True)
                stage(68, "OpenAI research complete; validating profile…")
                self._log("INFO", "PROFILE_RESEARCH_PROVIDER_OK", name=name, provider="openai_web")
            except Exception as exc:
                openai_error = exc
                self._log("WARNING", "PROFILE_RESEARCH_PROVIDER_FAILED", name=name, provider="openai_web", error=str(exc))

        if profile is None and s.local_ai_enabled:
            try:
                stage(24, "OpenAI path unavailable; trying public web + local AI…")
                self._log("INFO", "PROFILE_RESEARCH_PROVIDER_BEGIN", name=name, provider="web_plus_local_ai")
                ref = WikipediaProfileProvider().fetch_summary(name)
                provider = OllamaProvider(s.ollama_base_url, s.ollama_model, s.ollama_executable)
                prompt = f"""
You are structuring a candidate profile for a NON-PARTISAN fictional U.S. election simulator.
Use ONLY the supplied public reference text as factual evidence. Do not invent documented political
positions. Unknown is acceptable. Model-estimated traits must be clearly treated as game inputs.

Person requested: {name!r}
Reference title: {ref['title']}
Reference URL: {ref['url']}
Reference text:
{ref['summary']}

Return ONLY JSON with: canonical_name, profile_type, party, home_state, birth_year, career,
ideology (-100 to 100, 0 if unknown), national_appeal (-8 to 8), charisma, debate_skill,
experience, name_recognition (all 0-100), known_positions, inferred_positions, controversies,
confidence (0-1), profile_status. Keep known_positions strictly supported by the supplied text.
"""
                text = provider.chat(prompt)
                start, end = text.find("{"), text.rfind("}")
                if start < 0 or end <= start:
                    raise RuntimeError("Local model did not return a JSON profile from the web reference.")
                profile = json.loads(text[start:end+1])
                profile.setdefault("canonical_name", ref["title"] or name)
                profile["source_type"] = "web_plus_local_ai"
                profile["sources"] = [{"title": ref["title"], "url": ref["url"], "what_it_supports": "Public reference text supplied to local AI"}]
                profile["snapshot_date"] = date.today().isoformat()
                self._log("INFO", "PROFILE_RESEARCH_PROVIDER_OK", name=name, provider="web_plus_local_ai")
            except Exception as exc:
                local_error = exc
                self._log("WARNING", "PROFILE_RESEARCH_PROVIDER_FAILED", name=name, provider="web_plus_local_ai", error=str(exc))

        if profile is None:
            try:
                stage(42, "Trying conservative public-web profile fallback…")
                self._log("INFO", "PROFILE_RESEARCH_PROVIDER_BEGIN", name=name, provider="web_reference")
                profile = WikipediaProfileProvider().basic_profile(name)
                self._log("INFO", "PROFILE_RESEARCH_PROVIDER_OK", name=name, provider="web_reference")
            except Exception as web_exc:
                details = []
                if openai_error:
                    details.append(f"OpenAI: {openai_error}")
                if local_error:
                    details.append(f"Local AI fallback: {local_error}")
                details.append(f"Web fallback: {web_exc}")
                raise RuntimeError("Profile research failed across enabled provider paths. " + " | ".join(details)) from web_exc

        # Cache the researched profile immediately. Portrait acquisition is intentionally
        # handled by the UI as a separate background task in 0.10 so a slow Wikimedia
        # response cannot make Research + Cache look like it silently hung after the
        # useful profile data was already available.
        stage(86, "Saving enriched profile to the Knowledge Vault…")
        self.vault.upsert_profile(profile)
        saved = self.vault.get_profile(profile.get("canonical_name") or name) or profile
        stage(100, "Profile enriched and cached for offline use.")
        return saved

    def local_enrich_and_cache(self, name: str) -> dict[str, Any]:
        s = self.settings.settings
        if not s.local_ai_enabled:
            raise RuntimeError("Local AI is disabled in Settings.")
        provider = OllamaProvider(s.ollama_base_url, s.ollama_model, s.ollama_executable)
        prompt = f"""
Create a compact JSON simulation profile for {name!r} using only what you already know.
Do not claim uncertain political positions as documented facts. Put uncertain mappings in inferred_positions.
Return only JSON with: canonical_name, profile_type, party, home_state, birth_year, career,
ideology (-100 to 100, 0 if unknown), national_appeal (-8 to 8), charisma, debate_skill,
experience, name_recognition (all 0-100), known_positions, inferred_positions, controversies,
confidence (0-1), profile_status. This is a game-model estimate, not an objective judgment.
"""
        text = provider.chat(prompt)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Local model did not return a JSON profile.")
        profile = json.loads(text[start:end+1])
        profile.setdefault("canonical_name", name)
        profile["source_type"] = "local_ai_inference"
        profile["snapshot_date"] = date.today().isoformat()
        self.vault.upsert_profile(profile)
        return self.vault.get_profile(profile["canonical_name"]) or profile
