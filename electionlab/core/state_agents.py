from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

ISSUES = [
    "Economy", "Cost of living", "Healthcare", "Immigration", "Public safety",
    "Foreign policy", "Character/leadership", "Democracy/institutions",
]

ISSUE_AFFINITY = {
    ("Economy", "Cost of living"): 0.78,
    ("Cost of living", "Economy"): 0.78,
    ("Public safety", "Immigration"): 0.35,
    ("Immigration", "Public safety"): 0.35,
    ("Character/leadership", "Democracy/institutions"): 0.40,
    ("Democracy/institutions", "Character/leadership"): 0.40,
}

REGION_ALIASES = {
    "South": {"AL","AR","FL","GA","KY","LA","MS","NC","OK","SC","TN","TX","VA","WV"},
    "Rust Belt": {"PA","MI","WI","OH"},
    "Sun Belt": {"AZ","NV","GA","NC","TX","FL"},
    "Midwest": {"WI","MI","MN","IA","OH","MO","IL","IN","KS","NE"},
    "Northeast": {"PA","NY","NJ","NH","ME","MA","CT","RI","VT","DE","MD"},
}

class StateAgentModel:
    """Lightweight independent electorate agents for all 50 states + D.C.

    These agents are numerical and deterministic. They are designed to run every campaign turn
    without requiring 51 LLM calls. AI providers may *narrate* a selected state's concerns or
    result, but they do not own the underlying state opinion state.
    """

    def __init__(self):
        raw = json.loads((DATA_DIR / "state_context_2024.json").read_text(encoding="utf-8"))
        self.metadata = {k:v for k,v in raw.items() if k != "states"}
        self.states: dict[str, dict[str, Any]] = raw["states"]

    @staticmethod
    def _rng(*parts: Any) -> random.Random:
        material = "|".join(str(x) for x in parts)
        seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
        return random.Random(seed)

    def ensure_campaign(self, campaign: dict[str, Any]) -> None:
        opinion = campaign.setdefault("state_opinion", {})
        for code in self.states:
            row = opinion.setdefault(code, {})
            row.setdefault("support_delta_a", 0.0)
            row.setdefault("attention_a", 0.0)
            row.setdefault("attention_b", 0.0)
            row.setdefault("issue_hits_a", {})
            row.setdefault("issue_hits_b", {})
            row.setdefault("last_touch_a", None)
            row.setdefault("last_touch_b", None)
        campaign.setdefault("constituent_conversations", 0)

    @staticmethod
    def _issue_match(message: str, issue: str) -> float:
        if message == issue:
            return 1.0
        return ISSUE_AFFINITY.get((message, issue), 0.12)

    def target_states(self, region: str) -> tuple[list[str], float]:
        if not region or region == "National":
            return list(self.states), 0.28
        codes = REGION_ALIASES.get(region)
        if codes:
            return [c for c in self.states if c in codes], 1.0
        return list(self.states), 0.20

    def apply_strategy(self, campaign: dict[str, Any], side: str, strategy: dict[str, str]) -> dict[str, Any]:
        self.ensure_campaign(campaign)
        side = side.upper()
        sign = 1.0 if side == "A" else -1.0
        region = strategy.get("region") or "National"
        message = strategy.get("message") or "Economy"
        tone = strategy.get("tone") or "Positive"
        codes, intensity = self.target_states(region)
        tone_factor = {"Positive": 1.00, "Contrast": 0.92, "Aggressive": 0.78}.get(tone, 0.90)
        rng = self._rng(campaign.get("seed"), campaign.get("turn"), side, region, message, tone)
        moved: list[tuple[str, float]] = []
        for code in codes:
            ctx = self.states[code]
            priorities = ctx.get("issue_priorities") or {}
            # A message can resonate with more than one priority (e.g. Economy helps COL concerns).
            resonance = max((float(weight) * self._issue_match(message, issue) for issue, weight in priorities.items()), default=0.25)
            # Tiny deterministic local variation keeps two otherwise-similar states from moving identically.
            local = rng.uniform(0.90, 1.10)
            delta = sign * intensity * tone_factor * resonance * local * 0.34
            # Diminishing returns from repeatedly hitting the exact same state/issue.
            row = campaign["state_opinion"][code]
            hit_key = "issue_hits_a" if side == "A" else "issue_hits_b"
            previous = float((row.get(hit_key) or {}).get(message, 0.0))
            delta *= max(0.48, 1.0 - min(previous, 8.0) * 0.055)
            row["support_delta_a"] = round(max(-8.0, min(8.0, float(row.get("support_delta_a", 0.0)) + delta)), 3)
            att_key = "attention_a" if side == "A" else "attention_b"
            row[att_key] = round(float(row.get(att_key, 0.0)) + intensity, 2)
            row[hit_key][message] = round(previous + intensity, 2)
            row["last_touch_a" if side == "A" else "last_touch_b"] = campaign.get("current_date")
            moved.append((code, delta))
        moved.sort(key=lambda x: abs(x[1]), reverse=True)
        return {
            "side": side,
            "region": region,
            "message": message,
            "tone": tone,
            "states_touched": len(codes),
            "largest_effects": [{"state": c, "delta_a": round(d, 3)} for c,d in moved[:5]],
            "fictional_model_effect": True,
        }


    def apply_state_operation(self, campaign: dict[str, Any], side: str, code: str, operation: str, message: str) -> dict[str, Any]:
        """Apply one focused campaign operation to a single state.

        This is deterministic campaign-game math, not an AI judgment. Operations
        trade campaign funds for attention and persuasion, with diminishing returns.
        """
        self.ensure_campaign(campaign)
        side = (side or "A").upper()
        code = (code or "").upper()
        if code not in self.states:
            raise ValueError("Choose a valid state before running a state operation.")
        if side not in {"A", "B"}:
            raise ValueError("State operation side must be Ticket A or Ticket B.")
        operation = operation or "Rally"
        message = message or "Economy"
        specs = {
            "Rally": {"cost": 2.0, "attention": 1.35, "persuasion": 0.42},
            "Town Hall": {"cost": 1.4, "attention": 1.05, "persuasion": 0.56},
            "Ad Buy": {"cost": 3.8, "attention": 1.75, "persuasion": 0.38},
            "Field Organizing": {"cost": 4.6, "attention": 2.15, "persuasion": 0.31},
        }
        spec = specs.get(operation, specs["Rally"])
        ctx = self.states[code]
        priorities = ctx.get("issue_priorities") or {}
        resonance = max((float(weight) * self._issue_match(message, issue) for issue, weight in priorities.items()), default=.25)
        row = campaign["state_opinion"][code]
        hit_key = "issue_hits_a" if side == "A" else "issue_hits_b"
        att_key = "attention_a" if side == "A" else "attention_b"
        previous = float((row.get(hit_key) or {}).get(message, 0.0))
        # Dedicated state operations are more potent than a broad regional turn,
        # but repeated saturation of the same state/issue tails off strongly.
        diminish = max(.34, 1.0 - min(previous, 10.0) * .065)
        rng = self._rng(campaign.get("seed"), "state-operation", campaign.get("turn", 0), side, code, operation, message, round(previous, 2))
        local = rng.uniform(.93, 1.07)
        sign = 1.0 if side == "A" else -1.0
        delta = sign * float(spec["persuasion"]) * resonance * diminish * local
        row["support_delta_a"] = round(max(-8.0, min(8.0, float(row.get("support_delta_a", 0.0)) + delta)), 3)
        row[att_key] = round(float(row.get(att_key, 0.0)) + float(spec["attention"]), 2)
        row[hit_key][message] = round(previous + float(spec["attention"]), 2)
        row["last_touch_a" if side == "A" else "last_touch_b"] = campaign.get("current_date")
        field_key = "field_strength_a" if side == "A" else "field_strength_b"
        if operation == "Field Organizing":
            row[field_key] = round(min(10.0, float(row.get(field_key, 0.0)) + 1.0), 2)
        return {
            "side": side, "state": code, "state_name": ctx.get("name", code),
            "operation": operation, "message": message, "cost": float(spec["cost"]),
            "attention_added": float(spec["attention"]), "delta_a": round(delta, 3),
            "resonance": round(resonance, 3), "fictional_model_effect": True,
        }

    def campaign_adjustments(self, campaign: dict[str, Any]) -> dict[str, float]:
        self.ensure_campaign(campaign)
        return {code: float(row.get("support_delta_a", 0.0)) for code,row in campaign["state_opinion"].items()}

    def context_for(self, code: str, campaign: dict[str, Any] | None = None) -> dict[str, Any]:
        code = (code or "").upper()
        ctx = dict(self.states.get(code) or {})
        if campaign is not None:
            self.ensure_campaign(campaign)
            ctx["campaign_opinion"] = dict(campaign["state_opinion"].get(code) or {})
        return ctx

    def constituent_context(self, campaign: dict[str, Any], state_code: str | None = None) -> dict[str, Any]:
        self.ensure_campaign(campaign)
        count = 1 + sum(1 for x in campaign.get("timeline", []) if x.get("type") == "conversation_exchange" and str(x.get("role","")).lower() == "constituent")
        if state_code and state_code.upper() in self.states:
            code = state_code.upper()
        else:
            # Prefer competitive states, but still allow the whole country.
            weighted=[]
            for c,ctx in self.states.items():
                margin=abs(float(ctx.get("dem_margin_2024",0)))
                weight=max(0.35, 4.5-min(margin,30)/8)
                weighted.extend([c]*max(1,round(weight)))
            rng=self._rng(campaign.get("seed"), "constituent", count)
            code=rng.choice(weighted)
        ctx=self.context_for(code,campaign)
        priorities=ctx.get("issue_priorities") or {}
        rng=self._rng(campaign.get("seed"), "constituent-issue", count, code)
        pool=[]
        for issue,w in priorities.items():
            pool.extend([issue]*max(1,round(float(w)*10)))
        issue=rng.choice(pool or ["Economy"])
        concern=self._concern_text(code,issue,ctx)
        opinion=ctx.get("campaign_opinion") or {}
        hits_a=float((opinion.get("issue_hits_a") or {}).get(issue,0) or 0)
        hits_b=float((opinion.get("issue_hits_b") or {}).get(issue,0) or 0)
        movement=float(opinion.get("support_delta_a",0) or 0)
        if hits_a > hits_b + .35:
            reaction=f"Ticket A has paid noticeably more campaign attention to this concern here ({hits_a:.1f} vs {hits_b:.1f} modeled issue touches)."
        elif hits_b > hits_a + .35:
            reaction=f"Ticket B has paid noticeably more campaign attention to this concern here ({hits_b:.1f} vs {hits_a:.1f} modeled issue touches)."
        elif hits_a + hits_b > .2:
            reaction="Both tickets have addressed this concern at roughly similar levels so far."
        else:
            reaction="Neither ticket has meaningfully focused on this concern here yet."
        if abs(movement) >= .15:
            reaction += f" The state's accumulated campaign movement is {movement:+.2f} points toward Ticket A."
        return {
            "state_code":code,"state_name":ctx.get("name",code),"issue":issue,
            "concern":concern,"campaign_reaction":reaction,"context":ctx
        }

    @staticmethod
    def _concern_text(code: str, issue: str, ctx: dict[str, Any]) -> str:
        if issue == "Cost of living":
            return f"Housing and everyday costs are a concern; the 2024 ACS median gross rent is about ${ctx.get('median_gross_rent',0):,.0f}/month."
        if issue == "Economy":
            return f"Jobs and household finances are a concern; the 2024 ACS unemployment estimate is {ctx.get('acs_unemployment_rate',0):.1f}% and median household income is about ${ctx.get('median_household_income',0):,.0f}."
        if issue == "Healthcare":
            return "Healthcare affordability and access are a modeled concern; this first state-data pack does not yet attach a healthcare indicator, so salience is neutral rather than invented."
        return f"{issue} is a modeled concern in this state. Its current salience is a simulation input, not a claim about every voter."

    def state_reason(self, code: str, campaign: dict[str, Any] | None = None) -> str:
        ctx=self.context_for(code,campaign)
        top=ctx.get("top_issues") or []
        parts=[]
        if top:
            parts.append("top modeled priorities: " + ", ".join(top[:3]))
        parts.append(f"2024 partisan baseline {float(ctx.get('dem_margin_2024',0)):+.1f} D")
        if campaign is not None:
            adj=float((ctx.get("campaign_opinion") or {}).get("support_delta_a",0))
            parts.append(f"campaign movement {adj:+.2f} pts toward Ticket A")
        return "; ".join(parts)
