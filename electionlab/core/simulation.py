from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@dataclass
class SimulationConfig:
    mode: str
    runs: int
    seed: str
    factors: dict[str, bool]
    national_environment: float = 0.0  # positive favors Ticket A, percentage points
    state_adjustments: dict[str, float] | None = None  # campaign/state-agent movement, positive toward A


MODE_PARAMS = {
    "Arcade": {"national_sd": 5.5, "state_sd": 6.5, "candidate_scale": 0.13, "analysis_weight": 0.55},
    "Analytical 1": {"national_sd": 3.6, "state_sd": 4.0, "candidate_scale": 0.09, "analysis_weight": 0.72},
    "Analytical 2": {"national_sd": 2.8, "state_sd": 3.0, "candidate_scale": 0.07, "analysis_weight": 0.86},
    "Forecast Lab": {"national_sd": 2.3, "state_sd": 2.5, "candidate_scale": 0.055, "analysis_weight": 1.0},
}


class ElectionEngine:
    def __init__(self):
        self.states = json.loads((DATA_DIR / "states.json").read_text(encoding="utf-8"))
        context_raw = json.loads((DATA_DIR / "state_context_2024.json").read_text(encoding="utf-8"))
        self.state_context = context_raw.get("states", {})
        self.state_context_metadata = {k: v for k, v in context_raw.items() if k != "states"}

    @staticmethod
    def _seed_int(seed: str) -> int:
        digest = hashlib.sha256(seed.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big")

    @staticmethod
    def _party_side(party: str | None) -> int:
        p = (party or "").lower()
        if "dem" in p or "progress" in p or "left" in p:
            return 1
        if "rep" in p or "conserv" in p or "right" in p:
            return -1
        return 0

    @staticmethod
    def _candidate_effect(candidate: dict[str, Any], mode: str, factors: dict[str, bool]) -> float:
        params = MODE_PARAMS.get(mode, MODE_PARAMS["Analytical 2"])
        effect = float(candidate.get("national_appeal", 0) or 0)
        if factors.get("candidate_personality", True):
            effect += (float(candidate.get("charisma", 50)) - 50) * params["candidate_scale"]
        if factors.get("debates", True):
            effect += (float(candidate.get("debate_skill", 50)) - 50) * params["candidate_scale"] * 0.45
        if factors.get("experience", True):
            effect += (float(candidate.get("experience", 50)) - 50) * params["candidate_scale"] * 0.35
        if factors.get("name_recognition", True):
            effect += (float(candidate.get("name_recognition", 50)) - 50) * params["candidate_scale"] * 0.25
        return max(-8.0, min(8.0, effect))

    @staticmethod
    def _local_overview(states: list[dict[str, Any]], prob_a: float, expected_ev_a: float, pop_margin: float, a: dict[str, Any], b: dict[str, Any]) -> str:
        an=a.get("canonical_name") or a.get("name") or "Ticket A"
        bn=b.get("canonical_name") or b.get("name") or "Ticket B"
        winner=an if prob_a >= .5 else bn
        close=sorted(states,key=lambda x:abs(float(x.get("avg_margin_a",0))))[:5]
        battlegrounds=", ".join(f"{x['code']} ({'A' if x['avg_margin_a']>=0 else 'B'} {abs(x['avg_margin_a']):.1f})" for x in close)
        ev_a=round(expected_ev_a); ev_b=538-ev_a
        return (f"{winner} is the more likely winner in this simulation. Expected Electoral College: {an} {ev_a}, {bn} {ev_b}. "
                f"The modeled national popular-vote margin is {pop_margin:+.1f} points toward Ticket A. Closest states: {battlegrounds}.")

    def run(self, a: dict[str, Any], b: dict[str, Any], cfg: SimulationConfig, progress_callback=None) -> dict[str, Any]:
        params = MODE_PARAMS.get(cfg.mode, MODE_PARAMS["Analytical 2"])
        rng = random.Random(self._seed_int(cfg.seed))
        runs = max(100, min(int(cfg.runs), 50000))
        if progress_callback:
            progress_callback(0, f"Preparing {runs:,} simulated elections…")

        party_a = self._party_side(a.get("party"))
        party_b = self._party_side(b.get("party"))
        candidate_delta = self._candidate_effect(a, cfg.mode, cfg.factors) - self._candidate_effect(b, cfg.mode, cfg.factors)

        # If the tickets are conventional D vs R, the starter state baseline is meaningful.
        # For other pairings, ideology provides a weaker translation and uncertainty rises.
        conventional = {party_a, party_b} == {1, -1}
        orientation = 1
        if conventional and party_a == -1:
            orientation = -1

        state_wins = {s["code"]: 0 for s in self.states}
        state_margin_sum = {s["code"]: 0.0 for s in self.states}
        ev_a_runs: list[int] = []
        popular_margin_runs: list[float] = []
        presidency_wins_a = 0

        progress_step = max(1, runs // 20)
        for run_index in range(runs):
            national_shock = rng.gauss(0, params["national_sd"])
            if not cfg.factors.get("random_uncertainty", True):
                national_shock = 0.0
            national = cfg.national_environment + candidate_delta + national_shock
            ev_a = 0
            weighted_margin = 0.0
            pop_weight = 0.0

            for s in self.states:
                baseline = float(s["dem_margin_2024"])
                if conventional:
                    baseline *= orientation
                else:
                    ideology_a = float(a.get("ideology", 0) or 0)
                    ideology_b = float(b.get("ideology", 0) or 0)
                    ideological_match = ((-baseline / 20.0) * (ideology_b - ideology_a))
                    baseline = baseline * 0.30 + ideological_match

                if not cfg.factors.get("historical_baseline", True):
                    baseline = 0.0
                state_noise = rng.gauss(0, params["state_sd"]) if cfg.factors.get("random_uncertainty", True) else 0.0
                home_effect = 0.0
                if cfg.factors.get("home_state", True):
                    if (a.get("home_state") or "").upper() == s["code"]:
                        home_effect += 1.4
                    if (b.get("home_state") or "").upper() == s["code"]:
                        home_effect -= 1.4
                    if (a.get("vp_home_state") or "").upper() == s["code"]:
                        home_effect += 0.6
                    if (b.get("vp_home_state") or "").upper() == s["code"]:
                        home_effect -= 0.6
                campaign_adjustment = float((cfg.state_adjustments or {}).get(s["code"], 0.0))
                margin = baseline * params["analysis_weight"] + national + home_effect + campaign_adjustment + state_noise
                state_margin_sum[s["code"]] += margin
                if margin > 0:
                    ev_a += int(s["ev"])
                    state_wins[s["code"]] += 1
                weighted_margin += margin * float(s.get("population_weight", s["ev"]))
                pop_weight += float(s.get("population_weight", s["ev"]))

            ev_a_runs.append(ev_a)
            popular_margin_runs.append(weighted_margin / max(pop_weight, 1.0))
            if ev_a >= 270:
                presidency_wins_a += 1
            if progress_callback and (run_index == 0 or (run_index + 1) % progress_step == 0 or run_index + 1 == runs):
                pct = int(((run_index + 1) / runs) * 88)
                progress_callback(pct, f"Simulating election universes… {run_index + 1:,}/{runs:,}")

        if progress_callback:
            progress_callback(90, "Summarizing state probabilities and model drivers…")
        states_out = []
        for s in self.states:
            code = s["code"]
            prob_a = state_wins[code] / runs
            avg_margin = state_margin_sum[code] / runs
            raw_baseline = float(s["dem_margin_2024"])
            baseline_component = raw_baseline * orientation * params["analysis_weight"] if conventional else raw_baseline * 0.30 * params["analysis_weight"]
            if not cfg.factors.get("historical_baseline", True):
                baseline_component = 0.0
            home_effect = 0.0
            if cfg.factors.get("home_state", True):
                if (a.get("home_state") or "").upper() == code: home_effect += 1.4
                if (b.get("home_state") or "").upper() == code: home_effect -= 1.4
                if (a.get("vp_home_state") or "").upper() == code: home_effect += 0.6
                if (b.get("vp_home_state") or "").upper() == code: home_effect -= 0.6
            campaign_adjustment = float((cfg.state_adjustments or {}).get(code, 0.0))
            national_component = cfg.national_environment + candidate_delta
            leader = "Ticket A" if avg_margin >= 0 else "Ticket B"
            dominant = max(
                [("state baseline", abs(baseline_component)), ("candidate/national factors", abs(national_component)), ("home-state effect", abs(home_effect)), ("campaign movement", abs(campaign_adjustment))],
                key=lambda x: x[1],
            )[0]
            ctx = self.state_context.get(code, {})
            priorities = list(ctx.get("top_issues") or [])[:3]
            priority_note = f" State context currently flags {', '.join(priorities)} as the highest modeled issue priorities." if priorities else ""
            reason = (
                f"{leader} is favored here by {abs(avg_margin):.1f} points on average. "
                f"The largest modeled driver is {dominant}; the state baseline contributes {baseline_component:+.1f}, "
                f"candidate/national factors {national_component:+.1f}, home-state effects {home_effect:+.1f}, "
                f"and campaign movement {campaign_adjustment:+.1f} points toward Ticket A.{priority_note}"
            )
            states_out.append({**s, "a_win_prob": prob_a, "avg_margin_a": avg_margin, "reason": reason,
                "factor_breakdown": {"baseline": baseline_component, "national_candidate": national_component, "home_state": home_effect, "campaign": campaign_adjustment},
                "state_context": {
                    "top_issues": priorities,
                    "median_household_income": ctx.get("median_household_income"),
                    "median_gross_rent": ctx.get("median_gross_rent"),
                    "acs_unemployment_rate": ctx.get("acs_unemployment_rate"),
                    "issue_priorities": ctx.get("issue_priorities", {}),
                    "basis": "2024 ACS indicators + transparent ElectionLab heuristic issue-priority layer",
                }})

        expected_ev_a = sum(s["ev"] * s["a_win_prob"] for s in states_out)
        median_ev_a = sorted(ev_a_runs)[len(ev_a_runs) // 2]
        avg_pop_margin = sum(popular_margin_runs) / len(popular_margin_runs)

        # Result intelligence is deterministic and derived only from the numerical
        # output. It adds useful election-analysis features without asking an LLM
        # to invent a story after the fact.
        projected_a = [s for s in states_out if s["avg_margin_a"] >= 0]
        projected_b = [s for s in states_out if s["avg_margin_a"] < 0]
        projected_a_ev = sum(int(s["ev"]) for s in projected_a)
        projected_b_ev = 538 - projected_a_ev
        closest = min(states_out, key=lambda x: abs(float(x["avg_margin_a"])))
        battlegrounds = [s for s in states_out if abs(float(s["avg_margin_a"])) <= 5.0]

        winner_side = "A" if projected_a_ev >= 270 else "B"
        if winner_side == "A":
            ordered = sorted(projected_a, key=lambda x: float(x["avg_margin_a"]), reverse=True)
        else:
            ordered = sorted(projected_b, key=lambda x: float(x["avg_margin_a"]))
        running_ev = 0
        tipping = None
        for state in ordered:
            running_ev += int(state["ev"])
            if running_ev >= 270:
                tipping = state
                break
        if tipping is None and states_out:
            tipping = closest

        biggest_departure = max(
            states_out,
            key=lambda x: abs(float(x["avg_margin_a"]) - float((x.get("factor_breakdown") or {}).get("baseline", 0.0))),
        )
        insights = {
            "projected_map_ev_a": projected_a_ev,
            "projected_map_ev_b": projected_b_ev,
            "closest_state": {"code": closest["code"], "name": closest["name"], "margin_a": closest["avg_margin_a"]},
            "tipping_point": {"code": tipping["code"], "name": tipping["name"], "margin_a": tipping["avg_margin_a"], "side": winner_side} if tipping else None,
            "battleground_count": len(battlegrounds),
            "battlegrounds": [s["code"] for s in sorted(battlegrounds, key=lambda x: abs(float(x["avg_margin_a"])))],
            "biggest_departure": {
                "code": biggest_departure["code"],
                "name": biggest_departure["name"],
                "margin_a": biggest_departure["avg_margin_a"],
                "baseline_component": (biggest_departure.get("factor_breakdown") or {}).get("baseline", 0.0),
            },
        }
        if progress_callback:
            progress_callback(100, "Election analysis complete.")

        return {
            "mode": cfg.mode,
            "seed": cfg.seed,
            "runs": runs,
            "ticket_a": a,
            "ticket_b": b,
            "a_presidency_prob": presidency_wins_a / runs,
            "b_presidency_prob": 1 - presidency_wins_a / runs,
            "expected_ev_a": expected_ev_a,
            "expected_ev_b": 538 - expected_ev_a,
            "median_ev_a": median_ev_a,
            "median_ev_b": 538 - median_ev_a,
            "avg_popular_margin_a": avg_pop_margin,
            "states": states_out,
            "local_overview": self._local_overview(states_out, presidency_wins_a / runs, expected_ev_a, avg_pop_margin, a, b),
            "insights": insights,
            "limitations": [
                "Starter state baseline is an approximate 2024-derived snapshot, not live polling.",
                "Maine and Nebraska are still winner-take-all in pre-1.0 build 0.11.1; district allocation remains planned.",
                "Candidate trait scores are simulation inputs, not objective measurements.",
            ],
        }
