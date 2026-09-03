from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from electionlab.core.model_ids import normalize_openai_model

try:
    import keyring
except Exception:  # pragma: no cover
    keyring = None


SERVICE = "ElectionLab"
USERNAME = "openai_api_key"


def save_api_key(key: str) -> bool:
    if not keyring:
        return False
    try:
        keyring.set_password(SERVICE, USERNAME, key)
        return True
    except Exception:
        return False


def load_api_key() -> str | None:
    if not keyring:
        return None
    try:
        return keyring.get_password(SERVICE, USERNAME)
    except Exception:
        return None


def clear_api_key() -> None:
    if not keyring:
        return
    try:
        keyring.delete_password(SERVICE, USERNAME)
    except Exception:
        pass


class OpenAIResearchProvider:
    def __init__(self, model: str, api_key: str | None = None):
        self.model = normalize_openai_model(model)
        self.api_key = api_key or load_api_key()

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start, end = text.find("{"), text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start:end+1])
            raise


    def chat(self, prompt: str, system: str | None = None) -> str:
        if not self.api_key:
            raise RuntimeError("No OpenAI API key is configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is not installed.") from exc
        client = OpenAI(api_key=self.api_key, timeout=90.0, max_retries=2)
        pieces = []
        if system:
            pieces.append({"role": "system", "content": system})
        pieces.append({"role": "user", "content": prompt})
        response = client.responses.create(model=self.model, input=pieces, store=False)
        return response.output_text

    def configured(self) -> bool:
        return bool(self.api_key)

    def research_person(self, name: str, use_web: bool = True) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("No OpenAI API key is configured.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("The openai package is not installed.") from exc

        client = OpenAI(api_key=self.api_key, timeout=90.0, max_retries=2)
        prompt = f"""
Research the public figure named {name!r} for a NON-PARTISAN fictional U.S. election simulation.
Return ONLY one valid JSON object. Separate documented facts from model inference. Never invent a documented political position.
Use null/unknown when evidence is insufficient. Scores are game-model estimates, not objective truths.

Schema:
{{
  "canonical_name": string,
  "profile_type": "political"|"historical_political"|"public_figure"|"other",
  "source_type": "openai_web_research",
  "party": string|null,
  "home_state": two-letter state code|null,
  "birth_year": integer|null,
  "career": string|null,
  "office_years": string|null,
  "ideology": number from -100 (left) to 100 (right) or 0 if not responsibly inferable,
  "national_appeal": number from -8 to 8,
  "charisma": number 0-100,
  "debate_skill": number 0-100,
  "experience": number 0-100,
  "name_recognition": number 0-100,
  "known_positions": object mapping issue -> concise documented stance,
  "inferred_positions": object mapping issue -> concise explicitly inferred stance,
  "controversies": array of concise, material, well-supported items only,
  "sources": array of objects with title, url, and what_it_supports,
  "confidence": number 0-1,
  "profile_status": "researched",
  "snapshot_date": "{date.today().isoformat()}"
}}
Prefer primary/official sources and high-quality reporting. Keep the profile compact enough for local caching.
"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "store": False,
        }
        if use_web:
            kwargs["tools"] = [{"type": "web_search"}]
        response = client.responses.create(**kwargs)
        profile = self._extract_json(response.output_text)
        profile.setdefault("canonical_name", name)
        profile["source_type"] = "openai_web_research" if use_web else "openai_model"
        return profile
