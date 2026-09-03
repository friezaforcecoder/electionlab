from __future__ import annotations

from copy import deepcopy
from typing import Any

# Campaign rules live with each save. Global Settings should only describe the
# installation/provider environment (storage, API keys, local model, appearance).
# A campaign remains reproducible even if the user's global Settings later change.

RULE_PRESETS: dict[str, dict[str, Any]] = {
    "Arcade": {
        "description": "Fast, dramatic campaign game with bigger event/campaign effects and less analytical friction.",
        "simulation_mode": "Arcade",
        "campaign": {
            "debates": True,
            "state_operations": True,
            "media": True,
            "field": True,
            "rapid_response": True,
            "polling": True,
            "conversations": True,
            "resources": True,
            "random_events": True,
            "fundraising": True,
            "endorsements": True,
            "ai_history": True,
        },
        "electorate": {
            "state_priorities": True,
            "historical_baseline": True,
            "demographics": True,
            "economics": True,
            "turnout": True,
            "candidate_traits": True,
        },
        "data": {
            "live_polling": False,
            "live_events": False,
            "current_economics": False,
        },
        "ai": {
            "dialogue": True,
            "opponent_ai": True,
            "event_narration": True,
            "state_explanations": True,
        },
        "simulation": {
            "uncertainty": True,
            "campaign_effect_strength": 1.35,
            "monte_carlo_runs": 1500,
        },
    },
    "Campaign": {
        "description": "The intended balanced ElectionLab game: strategy, debates, polling, state priorities, resources and interaction.",
        "simulation_mode": "Analytical 1",
        "campaign": {
            "debates": True,
            "state_operations": True,
            "media": True,
            "field": True,
            "rapid_response": True,
            "polling": True,
            "conversations": True,
            "resources": True,
            "random_events": True,
            "fundraising": True,
            "endorsements": True,
            "ai_history": True,
        },
        "electorate": {
            "state_priorities": True,
            "historical_baseline": True,
            "demographics": True,
            "economics": True,
            "turnout": True,
            "candidate_traits": True,
        },
        "data": {
            "live_polling": False,
            "live_events": False,
            "current_economics": False,
        },
        "ai": {
            "dialogue": True,
            "opponent_ai": True,
            "event_narration": True,
            "state_explanations": True,
        },
        "simulation": {
            "uncertainty": True,
            "campaign_effect_strength": 1.0,
            "monte_carlo_runs": 3000,
        },
    },
    "Simulation": {
        "description": "Observer-focused campaign. Let both sides play while you watch the electorate, polls and timeline develop.",
        "simulation_mode": "Analytical 1",
        "campaign": {
            "debates": True,
            "state_operations": True,
            "media": True,
            "field": True,
            "rapid_response": True,
            "polling": True,
            "conversations": False,
            "resources": True,
            "random_events": True,
            "fundraising": True,
            "endorsements": True,
            "ai_history": True,
        },
        "electorate": {
            "state_priorities": True,
            "historical_baseline": True,
            "demographics": True,
            "economics": True,
            "turnout": True,
            "candidate_traits": True,
        },
        "data": {
            "live_polling": False,
            "live_events": False,
            "current_economics": False,
        },
        "ai": {
            "dialogue": False,
            "opponent_ai": True,
            "event_narration": True,
            "state_explanations": True,
        },
        "simulation": {
            "uncertainty": True,
            "campaign_effect_strength": 0.9,
            "monte_carlo_runs": 3000,
        },
    },
    "Analytical": {
        "description": "More restrained campaign movement with stronger fundamentals and analytical transparency.",
        "simulation_mode": "Analytical 2",
        "campaign": {
            "debates": True,
            "state_operations": True,
            "media": True,
            "field": True,
            "rapid_response": True,
            "polling": True,
            "conversations": True,
            "resources": True,
            "random_events": True,
            "fundraising": True,
            "endorsements": True,
            "ai_history": True,
        },
        "electorate": {
            "state_priorities": True,
            "historical_baseline": True,
            "demographics": True,
            "economics": True,
            "turnout": True,
            "candidate_traits": True,
        },
        "data": {
            "live_polling": False,
            "live_events": False,
            "current_economics": False,
        },
        "ai": {
            "dialogue": True,
            "opponent_ai": True,
            "event_narration": True,
            "state_explanations": True,
        },
        "simulation": {
            "uncertainty": True,
            "campaign_effect_strength": 0.65,
            "monte_carlo_runs": 5000,
        },
    },
    "Forecast Lab": {
        "description": "Maximum model transparency and uncertainty. Campaign effects are conservative and real-data modules are prioritized when available.",
        "simulation_mode": "Forecast Lab",
        "campaign": {
            "debates": True,
            "state_operations": True,
            "media": True,
            "field": True,
            "rapid_response": True,
            "polling": True,
            "conversations": False,
            "resources": True,
            "random_events": False,
            "fundraising": True,
            "endorsements": True,
            "ai_history": False,
        },
        "electorate": {
            "state_priorities": True,
            "historical_baseline": True,
            "demographics": True,
            "economics": True,
            "turnout": True,
            "candidate_traits": True,
        },
        "data": {
            "live_polling": False,
            "live_events": False,
            "current_economics": False,
        },
        "ai": {
            "dialogue": False,
            "opponent_ai": True,
            "event_narration": False,
            "state_explanations": True,
        },
        "simulation": {
            "uncertainty": True,
            "campaign_effect_strength": 0.4,
            "monte_carlo_runs": 10000,
        },
    },
}

# Controls that can be exposed in the New Game screen now. Data modules marked
# future=True are intentionally stored in the ruleset but not silently simulated.
RULE_CONTROLS = [
    ("campaign", "debates", "Debates", False),
    ("campaign", "state_operations", "State operations", False),
    ("campaign", "media", "Media buys", False),
    ("campaign", "field", "Field surges", False),
    ("campaign", "rapid_response", "Rapid response", False),
    ("campaign", "polling", "Simulation polling", False),
    ("campaign", "conversations", "Campaign conversations", False),
    ("campaign", "resources", "Campaign resources", False),
    ("campaign", "random_events", "Random campaign events", False),
    ("campaign", "fundraising", "Fundraising events", False),
    ("campaign", "endorsements", "Endorsement events", False),
    ("campaign", "ai_history", "AI history narration", False),
    ("electorate", "state_priorities", "State priorities", False),
    ("electorate", "historical_baseline", "Historical state baseline", False),
    ("electorate", "demographics", "Demographic context", False),
    ("electorate", "economics", "Economic context", False),
    ("electorate", "turnout", "Turnout modeling", False),
    ("electorate", "candidate_traits", "Candidate traits", False),
    ("ai", "dialogue", "AI dialogue", False),
    ("ai", "opponent_ai", "AI opponent", False),
    ("ai", "event_narration", "AI event narration", False),
    ("ai", "state_explanations", "AI state explanations", False),
    ("data", "live_polling", "Live real-world polling", True),
    ("data", "live_events", "Live current events", True),
    ("data", "current_economics", "Live/current economic data", True),
]


def preset_rules(name: str) -> dict[str, Any]:
    base = RULE_PRESETS.get(name) or RULE_PRESETS["Campaign"]
    return deepcopy(base)


def campaign_rules(campaign: dict[str, Any]) -> dict[str, Any]:
    preset = str(campaign.get("rules_preset") or "Campaign")
    merged = preset_rules(preset)
    rules = campaign.get("rules")
    if isinstance(rules, dict):
        for section, values in rules.items():
            if isinstance(values, dict) and isinstance(merged.get(section), dict):
                merged[section].update(values)
            else:
                merged[section] = deepcopy(values)
    return merged


def enabled(campaign: dict[str, Any], section: str, key: str, default: bool = True) -> bool:
    rules = campaign_rules(campaign)
    return bool((rules.get(section) or {}).get(key, default))


def modified_from_preset(preset_name: str, rules: dict[str, Any]) -> bool:
    return rules != preset_rules(preset_name)
