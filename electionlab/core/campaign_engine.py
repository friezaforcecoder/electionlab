from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .state_agents import StateAgentModel
from .rules import enabled as rule_enabled, preset_rules

PACE_DAYS = {
    "Highlights": 14,
    "Debate-to-Debate": 21,
    "Monthly": 30,
    "Weekly": 7,
    "Daily": 1,
    "Custom": 7,
}

REGIONS = {
    "National": [],
    "Rust Belt": ["PA", "MI", "WI", "OH"],
    "Sun Belt": ["AZ", "NV", "GA", "NC", "TX", "FL"],
    "Midwest": ["WI", "MI", "MN", "IA", "OH", "MO"],
    "Northeast": ["PA", "NY", "NJ", "NH", "ME", "MA"],
    "South": ["AL", "AR", "FL", "GA", "KY", "LA", "MS", "NC", "OK", "SC", "TN", "TX", "VA", "WV"],
}

MESSAGES = [
    "Economy", "Healthcare", "Immigration", "Public safety", "Foreign policy",
    "Character/leadership", "Democracy/institutions", "Cost of living",
]
TONES = ["Positive", "Contrast", "Aggressive"]

CAMPAIGN_OPERATION_SPECS = {
    "Fundraising Drive": {
        "rule": "fundraising",
        "cost": 0.0,
        "funds_min": 7.5,
        "funds_max": 15.0,
        "momentum_min": 0.02,
        "momentum_max": 0.16,
        "state_factor": 0.18,
        "headline": "fundraising drive expands campaign resources",
    },
    "Endorsement Push": {
        "rule": "endorsements",
        "cost": 1.5,
        "funds_min": 0.0,
        "funds_max": 0.0,
        "momentum_min": 0.12,
        "momentum_max": 0.42,
        "state_factor": 0.9,
        "headline": "endorsement push creates targeted momentum",
    },
    "Media Buy": {
        "rule": "media",
        "cost": 4.2,
        "national_cost": 7.0,
        "funds_min": 0.0,
        "funds_max": 0.0,
        "momentum_min": 0.05,
        "momentum_max": 0.20,
        "state_factor": 1.18,
        "headline": "paid media buy amplifies the campaign message",
    },
    "Field Surge": {
        "rule": "field",
        "cost": 5.5,
        "national_cost": 8.0,
        "funds_min": 0.0,
        "funds_max": 0.0,
        "momentum_min": 0.02,
        "momentum_max": 0.12,
        "state_factor": 0.72,
        "field_gain": 1.0,
        "headline": "field surge builds ground-game capacity",
    },
    "Rapid Response": {
        "rule": "rapid_response",
        "cost": 2.4,
        "funds_min": 0.0,
        "funds_max": 0.0,
        "momentum_min": -0.10,
        "momentum_max": 0.32,
        "state_factor": 0.45,
        "headline": "rapid response shapes the short-term news cycle",
    },
}


class CampaignEngine:
    def __init__(self):
        self.state_agents = StateAgentModel()

    """Deterministic campaign turn + milestone engine.

    Randomness is derived from the user-visible seed plus stable scenario inputs. 0.4
    incorrectly included the save UUID, which meant identical campaigns with the same
    seed could diverge. 0.5 intentionally removes that UUID from random material.

    The schedule is local simulation data. Real-world event ingestion remains a separate,
    sourced module so simulated events are never presented as actual news.
    """

    def ensure_state(self, campaign: dict[str, Any]) -> None:
        campaign.setdefault("rules_preset", "Campaign")
        campaign.setdefault("rules_modified", False)
        campaign.setdefault("rules", preset_rules(campaign.get("rules_preset") or "Campaign"))
        campaign.setdefault("current_date", "2028-06-01")
        campaign.setdefault("campaign_start_date", "2028-06-01")
        campaign.setdefault("election_date", "2028-11-07")
        campaign.setdefault("turn", 0)
        campaign.setdefault("momentum_a", 0.0)
        campaign.setdefault("momentum_b", 0.0)
        campaign.setdefault("funds_a", 100.0)
        campaign.setdefault("funds_b", 100.0)
        campaign.setdefault("state_focus_a", {})
        campaign.setdefault("state_focus_b", {})
        campaign.setdefault("operation_sequence", 0)
        campaign.setdefault("polling_history", [])
        campaign.setdefault("poll_sequence", 0)
        campaign.setdefault("timeline", [])
        campaign.setdefault("debates", [])
        campaign.setdefault("pending_event", None)
        campaign.setdefault("schedule", self._default_schedule(campaign))
        self.state_agents.ensure_campaign(campaign)
        # Upgrade old schedules in place without erasing statuses.
        known = {x.get("id") for x in campaign.get("schedule", [])}
        for item in self._default_schedule(campaign):
            if item["id"] not in known:
                campaign["schedule"].append(item)
        campaign["schedule"].sort(key=lambda x: x.get("date", "9999-12-31"))
        if not rule_enabled(campaign, "campaign", "debates", True):
            for item in campaign.get("schedule", []):
                if item.get("type") == "debate" and item.get("status") in {"scheduled", "missed"}:
                    item["status"] = "disabled"
            pending = campaign.get("pending_event") or {}
            if pending.get("type") == "debate":
                campaign["pending_event"] = None
                if campaign.get("status") == "event_pending":
                    campaign["status"] = "in_progress"
        # Migration behavior for campaigns that already advanced before the schedule system existed.
        # Past milestones are marked missed rather than suddenly interrupting an October save with a September debate.
        cur = date.fromisoformat(campaign["current_date"])
        for item in campaign.get("schedule", []):
            if item.get("status") != "scheduled":
                continue
            when = date.fromisoformat(item["date"])
            if when < cur:
                item["status"] = "missed"
            elif when == cur and item.get("type") == "debate" and not campaign.get("pending_event"):
                campaign["pending_event"] = dict(item)
                campaign["status"] = "event_pending"

    @staticmethod
    def _default_schedule(campaign: dict[str, Any]) -> list[dict[str, Any]]:
        election = date.fromisoformat(campaign.get("election_date", "2028-11-07"))
        milestones = [
            ("debate-1", election - timedelta(days=56), "Presidential Debate I", "debate", "Economy"),
            ("debate-2", election - timedelta(days=35), "Presidential Debate II", "debate", "Domestic policy"),
            ("debate-final", election - timedelta(days=21), "Final Presidential Debate", "debate", "Foreign policy"),
            ("election-day", election, "Election Day", "election_day", None),
        ]
        return [
            {
                "id": ident,
                "date": when.isoformat(),
                "title": title,
                "type": kind,
                "topic": topic,
                "status": "scheduled",
            }
            for ident, when, title, kind, topic in milestones
        ]

    @staticmethod
    def _scenario_material(campaign: dict[str, Any]) -> str:
        ta = campaign.get("ticket_a", {})
        tb = campaign.get("ticket_b", {})
        return "|".join([
            str(campaign.get("seed") or ""),
            str(ta.get("president") or ""),
            str(ta.get("vp") or ""),
            str(tb.get("president") or ""),
            str(tb.get("vp") or ""),
            str(campaign.get("election_date") or ""),
            str(campaign.get("turn", 0)),
        ])

    @classmethod
    def _rng(cls, campaign: dict[str, Any]) -> random.Random:
        n = int.from_bytes(hashlib.sha256(cls._scenario_material(campaign).encode()).digest()[:8], "big")
        return random.Random(n)

    @staticmethod
    def _event(rng: random.Random, side: str, person: str, strategy: dict[str, str]) -> dict[str, Any]:
        roll = rng.random()
        region = strategy.get("region", "National")
        message = strategy.get("message", "Economy")
        tone = strategy.get("tone", "Positive")
        if roll < .18:
            kind, delta, headline = "strong_event", rng.uniform(.3, 1.2), f"{person} lands a strong campaign moment"
        elif roll < .30:
            kind, delta, headline = "setback", -rng.uniform(.3, 1.1), f"{person} campaign deals with a rough news cycle"
        elif roll < .43:
            kind, delta, headline = "fundraising", rng.uniform(.05, .35), f"{person} reports a productive fundraising stretch"
        elif roll < .53:
            kind, delta, headline = "endorsement", rng.uniform(.15, .65), f"New endorsement gives {person} a modest boost"
        else:
            kind, delta, headline = "campaigning", rng.uniform(-.15, .35), f"{person} campaigns on {message.lower()} with a {tone.lower()} message"
        return {
            "type": kind,
            "side": side,
            "headline": headline,
            "momentum_delta": round(delta, 2),
            "region": region,
            "message": message,
            "tone": tone,
            "fictional_simulation_event": True,
        }

    @staticmethod
    def _party_code(party: str | None) -> str | None:
        p=(party or "").strip().lower()
        if p=="democratic": return "D"
        if p=="republican": return "R"
        return None

    def live_state_margin(self, campaign: dict[str, Any], code: str) -> float:
        """Fast latent campaign margin used by the War Room and simulated polls."""
        self.ensure_state(campaign)
        ctx=self.state_agents.states.get((code or "").upper()) or {}
        ta=campaign.get("ticket_a") or {}; tb=campaign.get("ticket_b") or {}
        pa=self._party_code(ta.get("party")); pb=self._party_code(tb.get("party"))
        dem=float(ctx.get("dem_margin_2024",0) or 0)
        if pa=="D" and pb=="R": base=dem
        elif pa=="R" and pb=="D": base=-dem
        else: base=0.0
        opinion=(campaign.get("state_opinion") or {}).get((code or "").upper()) or {}
        movement=float(opinion.get("support_delta_a",0) or 0)
        national=(float(campaign.get("momentum_a",0))-float(campaign.get("momentum_b",0)))*0.18
        return base+movement+national

    def generate_poll_snapshot(self, campaign: dict[str, Any], max_states: int = 8, force: bool = False) -> dict[str, Any]:
        """Generate seeded fictional battleground polls from the latent state model.

        These are intentionally noisy observations, not the state model itself and not
        real-world polling. Re-running the same campaign turn/seed reproduces them.
        """
        self.ensure_state(campaign)
        if not rule_enabled(campaign, "campaign", "polling", True):
            return {"disabled": True, "polls": [], "source": "Campaign rules: simulation polling disabled"}
        history=campaign.setdefault("polling_history",[])
        turn=int(campaign.get("turn",0))
        existing=next((x for x in reversed(history) if int(x.get("turn",-1))==turn and not x.get("manual_snapshot")),None)
        if existing and not force: return existing
        if force:
            campaign["poll_sequence"] = int(campaign.get("poll_sequence",0)) + 1
        sequence=int(campaign.get("poll_sequence",0)) if force else 0
        rows=[]
        candidates=[]
        for code,ctx in self.state_agents.states.items():
            margin=self.live_state_margin(campaign,code)
            candidates.append((abs(margin),code,ctx,margin))
        for _,code,ctx,latent in sorted(candidates)[:max(1,int(max_states))]:
            rng=self.state_agents._rng(campaign.get("seed"),"poll",turn,sequence,code)
            sample=rng.randint(720,1250)
            # Approximate polling noise in points. It deliberately can disagree with
            # the latent pulse while remaining seed-reproducible.
            noise=rng.gauss(0,2.35)
            observed=latent+noise
            moe=round(98.0/(sample**0.5),1)
            rows.append({
                "code":code,"state":ctx.get("name",code),"ev":int(ctx.get("ev",0)),
                "latent_margin_a":round(latent,2),"poll_margin_a":round(observed,2),
                "sample_size":sample,"moe":moe,
            })
        snap={
            "turn":turn,"date":campaign.get("current_date"),"polls":rows,
            "sequence":sequence,"manual_snapshot":bool(force),
            "source":"ElectionLab simulated battleground polling",
            "fictional_simulation_poll":True,
        }
        history.append(snap)
        # Keep saves compact while preserving meaningful trend history.
        if len(history)>80: del history[:-80]
        return snap

    def run_state_operation(self, campaign: dict[str, Any], side: str, code: str, operation: str, message: str) -> dict[str, Any]:
        self.ensure_state(campaign)
        if not rule_enabled(campaign, "campaign", "state_operations", True):
            raise RuntimeError("State Operations are disabled by this campaign's ruleset.")
        costs={"Rally":2.0,"Town Hall":1.4,"Ad Buy":3.8,"Field Organizing":4.6}
        cost=float(costs.get(operation,2.0))
        fund_key="funds_a" if side.upper()=="A" else "funds_b"
        available=float(campaign.get(fund_key,0) or 0)
        resources_on=rule_enabled(campaign,"campaign","resources",True)
        if resources_on and available < cost:
            raise RuntimeError(f"Not enough campaign funds for {operation}. Need {cost:.1f}; available {available:.1f}.")
        result=self.state_agents.apply_state_operation(campaign,side,code,operation,message)
        if resources_on:
            campaign[fund_key]=round(available-cost,2)
        else:
            cost=0.0
        result["cost"]=cost
        campaign.setdefault("timeline",[]).append({
            "type":"state_operation","date":campaign.get("current_date"),
            **result,"recorded_at":datetime.now(timezone.utc).isoformat(),
        })
        # A focused operation changes the electorate immediately, so invalidate a
        # same-turn poll snapshot rather than showing a stale poll as if it were new.
        campaign["polling_history"]=[x for x in campaign.get("polling_history",[]) if int(x.get("turn",-1)) != int(campaign.get("turn",0))]
        return result

    @staticmethod
    def _scale_added_state_effects(campaign: dict[str, Any], before: dict[str, float], factor: float) -> list[tuple[str, float]]:
        moved: list[tuple[str, float]] = []
        for code, row in campaign.get("state_opinion", {}).items():
            prior = float(before.get(code, 0.0))
            now = float(row.get("support_delta_a", 0.0) or 0.0)
            added = now - prior
            if abs(added) < 1e-9:
                continue
            adjusted = added * float(factor)
            row["support_delta_a"] = round(max(-8.0, min(8.0, prior + adjusted)), 3)
            moved.append((code, adjusted))
        moved.sort(key=lambda x: abs(x[1]), reverse=True)
        return moved

    def run_campaign_operation(self, campaign: dict[str, Any], side: str, operation: str, region: str, message: str, tone: str) -> dict[str, Any]:
        self.ensure_state(campaign)
        side = (side or "A").upper()
        if side not in {"A", "B"}:
            raise ValueError("Campaign operation side must be Ticket A or Ticket B.")
        operation = operation or "Fundraising Drive"
        spec = CAMPAIGN_OPERATION_SPECS.get(operation)
        if not spec:
            raise ValueError("Choose a valid campaign operation.")
        rule_key = str(spec.get("rule") or "")
        if rule_key and not rule_enabled(campaign, "campaign", rule_key, True):
            raise RuntimeError(f"{operation} is disabled by this campaign's ruleset.")

        region = region or "National"
        message = message or "Economy"
        tone = tone or "Positive"
        resources_on = rule_enabled(campaign, "campaign", "resources", True)
        fund_key = "funds_a" if side == "A" else "funds_b"
        cost = float(spec.get("national_cost", spec.get("cost", 0.0)) if region == "National" else spec.get("cost", 0.0))
        available = float(campaign.get(fund_key, 0.0) or 0.0)
        if resources_on and cost > available:
            raise RuntimeError(f"Not enough campaign funds for {operation}. Need {cost:.1f}; available {available:.1f}.")

        sequence = int(campaign.get("operation_sequence", 0) or 0) + 1
        campaign["operation_sequence"] = sequence
        rng = self.state_agents._rng(campaign.get("seed"), "campaign-operation", sequence, side, operation, region, message, tone, campaign.get("turn", 0))
        tone_funds = {"Positive": 1.08, "Contrast": 1.0, "Aggressive": 0.86}.get(tone, 1.0)
        funds_gained = round(rng.uniform(float(spec.get("funds_min", 0.0)), float(spec.get("funds_max", 0.0))) * tone_funds, 2)
        momentum_delta = round(rng.uniform(float(spec.get("momentum_min", 0.0)), float(spec.get("momentum_max", 0.0))), 2)

        if resources_on:
            campaign[fund_key] = round(max(0.0, available - cost + funds_gained), 2)
        else:
            cost = 0.0
            funds_gained = 0.0

        momentum_key = "momentum_a" if side == "A" else "momentum_b"
        campaign[momentum_key] = round(float(campaign.get(momentum_key, 0.0) or 0.0) + momentum_delta, 2)

        before = {code: float(row.get("support_delta_a", 0.0) or 0.0) for code, row in campaign.get("state_opinion", {}).items()}
        strategy_effect = self.state_agents.apply_strategy(campaign, side, {"region": region, "message": message, "tone": tone})
        moved = self._scale_added_state_effects(campaign, before, float(spec.get("state_factor", 1.0)))

        field_gain = float(spec.get("field_gain", 0.0) or 0.0)
        if field_gain:
            codes, _intensity = self.state_agents.target_states(region)
            field_key = "field_strength_a" if side == "A" else "field_strength_b"
            for code in codes:
                row = campaign["state_opinion"][code]
                row[field_key] = round(min(10.0, float(row.get(field_key, 0.0) or 0.0) + field_gain), 2)

        side_name = campaign.get("ticket_a", {}).get("president") if side == "A" else campaign.get("ticket_b", {}).get("president")
        headline = f"{side_name or f'Ticket {side}'} {spec.get('headline', 'runs a campaign operation')}"
        result = {
            "type": "campaign_operation",
            "date": campaign.get("current_date"),
            "side": side,
            "operation": operation,
            "region": region,
            "message": message,
            "tone": tone,
            "headline": headline,
            "cost": round(cost, 2),
            "funds_gained": funds_gained,
            "momentum_delta": momentum_delta,
            "states_touched": int(strategy_effect.get("states_touched", 0) or 0),
            "largest_effects": [{"state": code, "delta_a": round(delta, 3)} for code, delta in moved[:5]],
            "field_gain": field_gain,
            "fictional_model_effect": True,
        }
        campaign.setdefault("timeline", []).append({**result, "recorded_at": datetime.now(timezone.utc).isoformat()})
        campaign["polling_history"] = [x for x in campaign.get("polling_history", []) if int(x.get("turn", -1)) != int(campaign.get("turn", 0))]
        return result

    def next_scheduled_event(self, campaign: dict[str, Any], include_election_day: bool = True) -> dict[str, Any] | None:
        self.ensure_state(campaign)
        cur = date.fromisoformat(campaign["current_date"])
        candidates = []
        for item in campaign.get("schedule", []):
            if item.get("status") != "scheduled":
                continue
            if not include_election_day and item.get("type") == "election_day":
                continue
            when = date.fromisoformat(item["date"])
            if when >= cur:
                candidates.append(item)
        return min(candidates, key=lambda x: x["date"]) if candidates else None

    def _event_between(self, campaign: dict[str, Any], start: date, end: date) -> dict[str, Any] | None:
        candidates = []
        for item in campaign.get("schedule", []):
            if item.get("status") != "scheduled":
                continue
            when = date.fromisoformat(item["date"])
            if start < when <= end:
                candidates.append(item)
        return min(candidates, key=lambda x: x["date"]) if candidates else None

    def advance(self, campaign: dict[str, Any], pace: str, player_strategy: dict[str, str]) -> dict[str, Any]:
        self.ensure_state(campaign)
        if campaign.get("pending_event"):
            raise RuntimeError("Resolve or skip the current campaign event before advancing time.")

        start = date.fromisoformat(campaign["current_date"])
        election = date.fromisoformat(campaign["election_date"])

        if pace == "Instant Election":
            intended_end = election
        elif pace == "Debate-to-Debate":
            nxt = self.next_scheduled_event(campaign)
            intended_end = date.fromisoformat(nxt["date"]) if nxt else min(start + timedelta(days=21), election)
        else:
            intended_end = min(start + timedelta(days=PACE_DAYS.get(pace, 7)), election)

        milestone = self._event_between(campaign, start, intended_end)
        end = date.fromisoformat(milestone["date"]) if milestone else intended_end
        rng_key = self._scenario_material(campaign)
        rng = self._rng(campaign)
        agency = campaign.get("agency", "Spectate")

        ai_regions = list(REGIONS)
        strat_a = player_strategy if agency in {"Play Ticket A", "Control Both"} else {
            "region": rng.choice(ai_regions), "message": rng.choice(MESSAGES), "tone": rng.choice(TONES)
        }
        strat_b = player_strategy if agency in {"Play Ticket B", "Control Both"} else {
            "region": rng.choice(ai_regions), "message": rng.choice(MESSAGES), "tone": rng.choice(TONES)
        }

        a_name = campaign.get("ticket_a", {}).get("president") or "Ticket A"
        b_name = campaign.get("ticket_b", {}).get("president") or "Ticket B"
        if rule_enabled(campaign, "campaign", "random_events", True):
            events = [self._event(rng, "A", a_name, strat_a), self._event(rng, "B", b_name, strat_b)]
            if rng.random() < .28:
                env = rng.uniform(-.7, .7)
                events.append({
                    "type": "environment", "side": "shared",
                    "headline": "National political environment shifts modestly during the simulated news cycle",
                    "momentum_delta": round(env, 2), "fictional_simulation_event": True,
                })
                campaign["momentum_a"] += env
                campaign["momentum_b"] -= env
        else:
            events = [
                {"type":"campaigning","side":"A","headline":f"{a_name} executes the planned campaign strategy","momentum_delta":0.0,"region":strat_a.get("region","National"),"message":strat_a.get("message","Economy"),"tone":strat_a.get("tone","Positive"),"fictional_simulation_event":True},
                {"type":"campaigning","side":"B","headline":f"{b_name} executes the planned campaign strategy","momentum_delta":0.0,"region":strat_b.get("region","National"),"message":strat_b.get("message","Economy"),"tone":strat_b.get("tone","Positive"),"fictional_simulation_event":True},
            ]

        for ev in events:
            if ev["side"] == "A":
                campaign["momentum_a"] += ev["momentum_delta"]
            elif ev["side"] == "B":
                campaign["momentum_b"] += ev["momentum_delta"]

        for side, strat in [("a", strat_a), ("b", strat_b)]:
            focus = campaign[f"state_focus_{side}"]
            for code in REGIONS.get(strat.get("region", "National"), []):
                focus[code] = round(float(focus.get(code, 0)) + .15, 2)

        # Every state now maintains its own lightweight opinion state. Strategy pays off more
        # where the chosen message matches that state's modeled issue priorities.
        if rule_enabled(campaign, "electorate", "state_priorities", True):
            before_a={code:float(row.get("support_delta_a",0) or 0) for code,row in campaign.get("state_opinion",{}).items()}
            state_effect_a = self.state_agents.apply_strategy(campaign, "A", strat_a)
            state_effect_b = self.state_agents.apply_strategy(campaign, "B", strat_b)
            strength=float(((campaign.get("rules") or {}).get("simulation") or {}).get("campaign_effect_strength",1.0) or 1.0)
            if abs(strength-1.0) > 1e-9:
                # Scale only movement added this turn, preserving prior history.
                for code,row in campaign.get("state_opinion",{}).items():
                    prior=before_a.get(code,0.0); now=float(row.get("support_delta_a",0) or 0)
                    row["support_delta_a"]=round(prior+(now-prior)*strength,4)
                state_effect_a["rules_strength_multiplier"]=strength; state_effect_b["rules_strength_multiplier"]=strength
        else:
            state_effect_a={"states_touched":0,"disabled_by_rules":True}; state_effect_b={"states_touched":0,"disabled_by_rules":True}

        if rule_enabled(campaign, "campaign", "resources", True):
            campaign["funds_a"] = max(0.0, campaign["funds_a"] - (1.6 if strat_a.get("region") != "National" else 1.0))
            campaign["funds_b"] = max(0.0, campaign["funds_b"] - (1.6 if strat_b.get("region") != "National" else 1.0))
        campaign["turn"] += 1
        campaign["current_date"] = end.isoformat()

        ledger = {
            "type": "campaign_turn",
            "turn": campaign["turn"],
            "from_date": start.isoformat(),
            "to_date": end.isoformat(),
            "pace": pace,
            "strategy_a": strat_a,
            "strategy_b": strat_b,
            "events": events,
            "momentum_a": round(campaign["momentum_a"], 2),
            "momentum_b": round(campaign["momentum_b"], 2),
            "state_agent_effects": {"A": state_effect_a, "B": state_effect_b},
            "seed_turn_key": rng_key,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        campaign["timeline"].append(ledger)
        self.generate_poll_snapshot(campaign)

        if milestone and milestone.get("type") != "election_day":
            campaign["pending_event"] = dict(milestone)
            campaign["status"] = "event_pending"
            campaign["timeline"].append({
                "type": "milestone_reached",
                "event_id": milestone.get("id"),
                "date": milestone.get("date"),
                "headline": milestone.get("title"),
                "event_type": milestone.get("type"),
                "fictional_simulation_event": True,
            })
        elif end >= election:
            campaign["status"] = "election_day_ready"
        else:
            campaign["status"] = "in_progress"
        return ledger

    def fast_forward_debate_policy(self, campaign: dict[str, Any], policy: str, profile_a: dict[str, Any] | None = None, profile_b: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Resolve all remaining scheduled debates before an Instant Election jump.

        policy: ``manual`` leaves them scheduled, ``skip`` marks them skipped, and ``auto``
        performs a deterministic non-AI debate simulation so fast-forward never requires a provider.
        """
        self.ensure_state(campaign)
        if policy == "manual":
            return []
        cur = date.fromisoformat(campaign["current_date"])
        election = date.fromisoformat(campaign["election_date"])
        out=[]
        for item in campaign.get("schedule", []):
            if item.get("type") != "debate" or item.get("status") != "scheduled":
                continue
            when=date.fromisoformat(item["date"])
            if not (cur < when < election):
                continue
            if policy == "skip":
                item["status"]="skipped"
                rec={"type":"debate_skipped","date":item["date"],"headline":f"{item.get('title')} skipped during Instant Election fast-forward","fictional_simulation_event":True}
            else:
                rng=self._rng({**campaign,"turn":campaign.get("turn",0)+len(out)+1})
                da=float((profile_a or {}).get("debate_skill",50) or 50)
                db=float((profile_b or {}).get("debate_skill",50) or 50)
                score_a=max(0,min(100,50+(da-db)*0.35+rng.gauss(0,7)))
                score_b=max(0,min(100,100-score_a+rng.gauss(0,3)))
                delta=max(-1.25,min(1.25,(score_a-score_b)/30))
                campaign["momentum_a"]+=delta; campaign["momentum_b"]-=delta
                item["status"]="auto"
                rec={"type":"debate_auto","date":item["date"],"headline":f"{item.get('title')} auto-simulated during fast-forward","score_a":round(score_a,1),"score_b":round(score_b,1),"momentum_delta_a":round(delta,2),"provider":"deterministic local model","fictional_simulation_event":True}
            campaign.setdefault("timeline",[]).append(rec); out.append(rec)
        return out

    def _mark_schedule(self, campaign: dict[str, Any], event_id: str | None, status: str) -> None:
        if not event_id:
            return
        for item in campaign.get("schedule", []):
            if item.get("id") == event_id:
                item["status"] = status
                break

    def resolve_pending_event(self, campaign: dict[str, Any], status: str, note: str | None = None) -> None:
        self.ensure_state(campaign)
        pending = campaign.get("pending_event") or {}
        self._mark_schedule(campaign, pending.get("id"), status)
        if pending:
            campaign.setdefault("timeline", []).append({
                "type": "milestone_resolved",
                "event_id": pending.get("id"),
                "date": pending.get("date"),
                "headline": pending.get("title"),
                "resolution": status,
                "note": note,
                "fictional_simulation_event": True,
            })
        campaign["pending_event"] = None
        campaign["status"] = "in_progress"

    def skip_pending_event(self, campaign: dict[str, Any]) -> None:
        pending = campaign.get("pending_event") or {}
        self.resolve_pending_event(campaign, "skipped", "Player skipped this campaign event.")
        campaign.setdefault("timeline", []).append({
            "type": "debate_skipped" if pending.get("type") == "debate" else "event_skipped",
            "date": pending.get("date"),
            "headline": f"{pending.get('title', 'Campaign event')} skipped",
            "fictional_simulation_event": True,
        })

    def apply_debate_result(self, campaign: dict[str, Any], result: dict[str, Any]) -> None:
        """Persist a playable debate exchange and translate modeled effect into momentum."""
        self.ensure_state(campaign)
        delta = max(-1.5, min(1.5, float(result.get("user_momentum_delta", 0) or 0)))
        side = result.get("user_side")
        if side == "A":
            campaign["momentum_a"] += delta
            campaign["momentum_b"] -= delta * 0.35
        elif side == "B":
            campaign["momentum_b"] += delta
            campaign["momentum_a"] -= delta * 0.35
        campaign.setdefault("debates", []).append(result)
        campaign.setdefault("timeline", []).append({
            "type": "debate_exchange",
            "at": result.get("recorded_at") or datetime.now(timezone.utc).isoformat(),
            "question": result.get("question"),
            "user_side": side,
            "user_score": result.get("user_score"),
            "opponent_score": result.get("opponent_score"),
            "headline": result.get("notable_moment") or "Debate exchange completed",
            "momentum_delta": round(delta, 2),
            "fictional_simulation_event": True,
        })
        self.resolve_pending_event(campaign, "completed", "Player participated in the debate.")

    def apply_auto_debate_result(self, campaign: dict[str, Any], result: dict[str, Any]) -> None:
        self.ensure_state(campaign)
        delta = max(-1.5, min(1.5, float(result.get("momentum_delta_a", 0) or 0)))
        campaign["momentum_a"] += delta
        campaign["momentum_b"] -= delta
        campaign.setdefault("debates", []).append(result)
        campaign.setdefault("timeline", []).append({
            "type": "debate_auto",
            "at": result.get("recorded_at") or datetime.now(timezone.utc).isoformat(),
            "headline": result.get("notable_moment") or "Debate auto-simulated",
            "score_a": result.get("score_a"),
            "score_b": result.get("score_b"),
            "momentum_delta_a": round(delta, 2),
            "fictional_simulation_event": True,
        })
        self.resolve_pending_event(campaign, "auto", "Debate was simulated automatically.")
