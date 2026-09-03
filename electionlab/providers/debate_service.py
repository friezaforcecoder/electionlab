from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from electionlab.core.database import KnowledgeVault
from electionlab.core.settings import SettingsManager
from electionlab.core.state_agents import StateAgentModel
from .ollama_provider import OllamaProvider
from .openai_provider import OpenAIResearchProvider


class DebateService:
    """AI-backed campaign conversations and debate interactions.

    All generated dialogue is simulation content. Public figures' generated words are never
    represented as real quotations. Auto provider mode tries local AI, including a best-effort
    Ollama startup, then OpenAI when remote calls are permitted and configured.
    """

    def __init__(self, settings: SettingsManager, vault: KnowledgeVault):
        self.settings = settings
        self.vault = vault
        self.state_agents = StateAgentModel()

    def _local(self):
        s = self.settings.settings
        if not s.local_ai_enabled:
            raise RuntimeError("Local AI is disabled in Settings.")
        return OllamaProvider(s.ollama_base_url, s.ollama_model, s.ollama_executable)

    def _openai(self):
        s = self.settings.settings
        if s.offline_lock:
            raise RuntimeError("Offline Lock is enabled. Remote OpenAI calls are blocked.")
        if not s.openai_enabled:
            raise RuntimeError("OpenAI is disabled in Settings.")
        return OpenAIResearchProvider(s.openai_model)

    def _chat(self, prompt: str, system: str, preference: str) -> tuple[str, str]:
        pref = preference.lower()
        if "local" in pref and "auto" not in pref:
            return "Local AI", self._local().chat(prompt, system=system)
        if "openai" in pref:
            return "OpenAI", self._openai().chat(prompt, system=system)

        errors = []
        s = self.settings.settings
        if s.local_ai_enabled:
            try:
                return "Local AI", self._local().chat(prompt, system=system)
            except Exception as exc:
                errors.append(f"Local AI: {exc}")
        if s.openai_enabled and not s.offline_lock:
            try:
                return "OpenAI", self._openai().chat(prompt, system=system)
            except Exception as exc:
                errors.append(f"OpenAI: {exc}")
        if not errors:
            raise RuntimeError("No AI provider is available. Enable Local AI or OpenAI in Settings.")
        raise RuntimeError("Auto provider could not complete the AI interaction. " + " | ".join(errors))

    def _profile_context(self, name: str) -> str:
        p = self.vault.get_profile(name) if name else None
        if not p:
            return f"Name: {name or 'Unknown'}\nNo structured Knowledge Vault profile is available. Do not invent documented positions."
        known = p.get("known_positions") or {}
        inferred = p.get("inferred_positions") or {}
        return (
            f"Name: {p.get('canonical_name')}\n"
            f"Background: {p.get('career') or 'unknown'}\n"
            f"Party: {p.get('party') or 'unknown'}\n"
            f"Documented positions: {json.dumps(known, ensure_ascii=False)}\n"
            f"Explicit model inferences: {json.dumps(inferred, ensure_ascii=False)}\n"
            "Treat documented positions as facts only when present. Anything else must be framed as simulation inference."
        )

    @staticmethod
    def _campaign_summary(campaign: dict[str, Any]) -> dict[str, Any]:
        return {
            "date": campaign.get("current_date"),
            "ticket_a": campaign.get("ticket_a"),
            "ticket_b": campaign.get("ticket_b"),
            "momentum_a": campaign.get("momentum_a", 0),
            "momentum_b": campaign.get("momentum_b", 0),
            "funds_a": campaign.get("funds_a", 100),
            "funds_b": campaign.get("funds_b", 100),
            "agency": campaign.get("agency"),
            "pending_event": campaign.get("pending_event"),
            "recent_timeline": (campaign.get("timeline") or [])[-4:],
        }

    def conversation_chat(self, campaign: dict[str, Any], role: str, message: str, preference: str, state_code: str | None = None) -> dict[str, Any]:
        role_key = role.strip().lower()
        summary = self._campaign_summary(campaign)
        constituent_meta = self.state_agents.constituent_context(campaign, state_code) if role_key == "constituent" else None
        role_prompts = {
            "campaign adviser": (
                "You are the player's in-game campaign strategy adviser. Give practical strategy grounded only in the supplied simulation state. "
                "Explain tradeoffs and uncertainty. Do not claim unsupplied real-world polling or news."
            ),
            "constituent": (
                "You are a fictional undecided constituent encountered during the campaign. Respond like a normal voter, not a strategist. "
                "Your state, issue concern, and current modeled campaign sentiment are supplied below. Let those conditions shape your reaction. "
                "If the campaign has repeatedly addressed a high-priority issue in your state, acknowledge that where appropriate; if it ignored the issue, you may remain skeptical. "
                "Do not claim to represent every voter or treat the model's state priorities as opinion polling."
            ),
            "campaign staff": (
                "You are a fictional senior campaign staff member. Discuss logistics, messaging, scheduling, field strategy, and internal tradeoffs in a candid but concise way."
            ),
            "volunteer": (
                "You are a fictional campaign volunteer. Speak conversationally about what volunteers are seeing and what help the campaign needs. Avoid inventing real-world facts."
            ),
            "donor": (
                "You are a fictional potential campaign donor. Ask about strategy, viability, priorities, and use of campaign resources. Do not imply actual money or transactions are taking place."
            ),
            "reporter": (
                "You are a fictional campaign reporter in an interview. Ask or answer in a probing, neutral journalistic style based only on the simulation state. Do not invent real-world reporting."
            ),
        }
        persona = role_prompts.get(role_key, role_prompts["campaign adviser"])
        prompt = f"""
ElectionLab fictional campaign conversation.
Conversation role: {role}
Player message: {message}

Current fictional campaign state:
{json.dumps(summary, ensure_ascii=False, default=str)}

Constituent/state context (only present for constituent role):
{json.dumps(constituent_meta, ensure_ascii=False, default=str) if constituent_meta else "none"}

{persona}
Keep the response useful and conversational. This is simulation dialogue, not a real quote or real voter testimony.
"""
        provider_name, reply = self._chat(prompt, "ElectionLab fictional campaign conversation system.", preference)
        out={"provider": provider_name, "role": role, "reply": reply.strip()}
        if constituent_meta:
            out["constituent"]={k:v for k,v in constituent_meta.items() if k != "context"}
        return out

    def election_overview(self, result: dict[str, Any], preference: str) -> dict[str, str]:
        """Generate an optional AI-written recap from ElectionLab's already-computed result.

        The provider does not decide who won. It only explains the local numerical output supplied
        here, which keeps the election result reproducible even when no AI provider is available.
        """
        close = sorted(result.get("states", []), key=lambda x: abs(float(x.get("avg_margin_a", 0))))[:10]
        payload = {
            "mode": result.get("mode"),
            "runs": result.get("runs"),
            "ticket_a": result.get("ticket_a", {}).get("display_name"),
            "ticket_b": result.get("ticket_b", {}).get("display_name"),
            "expected_ev_a": round(float(result.get("expected_ev_a", 0)), 1),
            "expected_ev_b": round(float(result.get("expected_ev_b", 0)), 1),
            "a_presidency_probability": round(float(result.get("a_presidency_prob", 0)), 4),
            "popular_margin_a": round(float(result.get("avg_popular_margin_a", 0)), 2),
            "closest_states": [
                {
                    "state": x.get("name"), "code": x.get("code"),
                    "margin_a": round(float(x.get("avg_margin_a", 0)), 2),
                    "a_win_probability": round(float(x.get("a_win_prob", 0)), 4),
                    "local_reason": x.get("reason"),
                }
                for x in close
            ],
        }
        prompt = f"""
ElectionLab has already completed a fictional/non-authoritative election simulation. You are NOT
predicting or changing the result. Explain the supplied model output neutrally and clearly.
Discuss the Electoral College picture, national modeled margin, the closest decisive states, and
what the local factor explanations say drove the outcome. Distinguish model assumptions from real
polling or observed votes. Do not advocate for either candidate or tell anyone how to vote.

Simulation output:
{json.dumps(payload, ensure_ascii=False, default=str)}

Write 3-6 concise paragraphs. This is an AI interpretation of ElectionLab model output.
"""
        provider_name, reply = self._chat(prompt, "Neutral analyst of already-computed ElectionLab simulation results.", preference)
        return {"provider": provider_name, "reply": reply.strip()}


    def narrate_campaign_turn(self, campaign: dict[str, Any], turn_event: dict[str, Any], preference: str) -> dict[str, str]:
        """Write a concise fictional news-style recap of one already-computed turn.

        This function never changes campaign math. It receives the deterministic event ledger
        and state-agent effects after the turn has already been resolved, then produces flavor
        text that can be replaced/re-generated without changing the seed universe.
        """
        a = (campaign.get("ticket_a") or {}).get("president") or "Ticket A"
        b = (campaign.get("ticket_b") or {}).get("president") or "Ticket B"
        payload = {
            "date_range": [turn_event.get("from_date"), turn_event.get("to_date")],
            "ticket_a": a,
            "ticket_b": b,
            "events": turn_event.get("events") or [],
            "strategy_a": turn_event.get("strategy_a") or {},
            "strategy_b": turn_event.get("strategy_b") or {},
            "state_agent_effects": turn_event.get("state_agent_effects") or {},
            "momentum_a": turn_event.get("momentum_a"),
            "momentum_b": turn_event.get("momentum_b"),
        }
        prompt = f"""
ElectionLab has ALREADY computed this fictional campaign turn. Do not alter any numbers, invent
real-world news, or claim the simulated event actually happened. Turn the supplied ledger into a
short in-game campaign-news recap: one headline plus 2-4 concise sentences. Mention the strongest
state reactions when useful. Keep the tone neutral between tickets. Everything described is
fictional simulation content.

Computed turn ledger:
{json.dumps(payload, ensure_ascii=False, default=str)}
"""
        provider_name, reply = self._chat(
            prompt,
            "Neutral writer for fictional ElectionLab campaign history. Never change computed outcomes.",
            preference,
        )
        return {"provider": provider_name, "reply": reply.strip()}

    # Kept for compatibility with 0.4 callers/extensions.
    def advisor_chat(self, campaign: dict[str, Any], message: str, preference: str) -> dict[str, str]:
        return self.conversation_chat(campaign, "Campaign adviser", message, preference)

    def generate_question(self, campaign: dict[str, Any], topic: str, preference: str) -> dict[str, str]:
        a = campaign.get("ticket_a", {}).get("president") or "Ticket A"
        b = campaign.get("ticket_b", {}).get("president") or "Ticket B"
        prompt = f"""
You are the neutral moderator of a FICTIONAL U.S. presidential campaign debate in ElectionLab.
Candidates: {a} and {b}. Topic: {topic}.
Write ONE concise, substantive question that both candidates can answer. Do not advocate for either
candidate or party. Do not assert invented facts. Return only the question text, no preamble.
"""
        provider_name, question = self._chat(prompt, "Neutral election-simulation debate moderator.", preference)
        question = question.strip()
        if not question:
            raise RuntimeError("The AI moderator returned an empty question.")
        return {"provider": provider_name, "question": question}

    def evaluate_exchange(
        self,
        campaign: dict[str, Any],
        question: str,
        user_side: str,
        user_answer: str,
        preference: str,
    ) -> dict[str, Any]:
        a = campaign.get("ticket_a", {}).get("president") or "Ticket A"
        b = campaign.get("ticket_b", {}).get("president") or "Ticket B"
        user_name = a if user_side == "A" else b
        opp_name = b if user_side == "A" else a
        prompt = f"""
ElectionLab fictional presidential debate simulation.
Question: {question}
The player is answering as {user_name} (Ticket {user_side}).
Player answer:
{user_answer}

Opponent profile context:
{self._profile_context(opp_name)}
Player profile context:
{self._profile_context(user_name)}

Generate a simulated response for {opp_name}. This must be clearly treated as FICTIONAL roleplay,
not a real quote. Stay consistent with documented positions when available; when unavailable, avoid
inventing a specific factual stance and answer at a broader campaign level.

Then neutrally evaluate both debate performances for clarity, responsiveness, consistency, command
of the issue, and likely broad-audience effectiveness. Do NOT score based on which ideology is
"correct". Return ONLY JSON:
{{
  "opponent_response": "...",
  "moderator_analysis": "...",
  "user_score": 0-100,
  "opponent_score": 0-100,
  "user_momentum_delta": -1.5 to 1.5,
  "notable_moment": "short headline"
}}
"""
        provider_name, text = self._chat(prompt, "Neutral debate simulator. Never present simulated dialogue as a real quote.", preference)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("The AI debate evaluator did not return valid JSON.")
        result = json.loads(text[start:end+1])
        result["provider"] = provider_name
        result["user_side"] = user_side
        result["user_name"] = user_name
        result["opponent_name"] = opp_name
        result["question"] = question
        result["user_answer"] = user_answer
        result["fictional_simulation_content"] = True
        result["recorded_at"] = datetime.now(timezone.utc).isoformat()
        return result

    def auto_debate(self, campaign: dict[str, Any], topic: str, preference: str) -> dict[str, Any]:
        a = campaign.get("ticket_a", {}).get("president") or "Ticket A"
        b = campaign.get("ticket_b", {}).get("president") or "Ticket B"
        prompt = f"""
ElectionLab FICTIONAL debate auto-simulation.
Debate topic: {topic}
Ticket A: {a}
Ticket B: {b}

Ticket A profile:
{self._profile_context(a)}

Ticket B profile:
{self._profile_context(b)}

Simulate the debate at a high level without writing a long transcript. Evaluate performance based on
clarity, responsiveness, consistency, command of the issue and broad-audience effectiveness, not
ideological correctness. Treat all candidate dialogue as fictional simulation. Return ONLY JSON:
{{
  "summary": "2-5 sentence neutral recap",
  "score_a": 0-100,
  "score_b": 0-100,
  "momentum_delta_a": -1.5 to 1.5,
  "notable_moment": "short fictional campaign headline"
}}
"""
        provider_name, text = self._chat(prompt, "Neutral ElectionLab debate auto-simulator.", preference)
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("The AI debate auto-simulator did not return valid JSON.")
        result = json.loads(text[start:end+1])
        result.update({
            "provider": provider_name,
            "topic": topic,
            "candidate_a": a,
            "candidate_b": b,
            "fictional_simulation_content": True,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
        return result
