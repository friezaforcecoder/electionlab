# ElectionLab 0.12 — game shell, campaign rules and operations

## Separation of concerns

**Global Settings** describe the installation environment: data location, offline lock, OpenAI/local-AI provider configuration, model IDs and related app behavior.

**Campaign Rules** describe the simulated game universe: which campaign systems, electorate factors and optional AI presentation systems are active for that save.

This separation makes portable saves reproducible and prevents a later global settings change from silently changing the rules of an existing campaign.

## Save fields

New campaigns persist:

- `rules_preset`
- `rules_modified`
- `rules`
- `simulation_mode`
- user-visible `seed`

The rules object is version-friendly and grouped into `campaign`, `electorate`, `data`, `ai`, and `simulation` sections.

## Campaign Operations

0.12 adds rule-gated Campaign Operations to the existing save-local rules structure:

- fundraising
- endorsements
- media buys
- field surges
- rapid response

Operations are deterministic campaign-engine actions. They can adjust funds, momentum, field strength and state-agent support effects, and they write timeline events into the campaign save. AI narration may describe an operation, but the numerical result comes from local engine code and the campaign seed.

## Official presets

Arcade, Campaign, Simulation, Analytical and Forecast Lab are immutable templates in `electionlab/core/rules.py`. The New Game UI receives a deep copy. Changing a toggle modifies only that new campaign.

## Backward compatibility

Campaigns created before 0.11 are upgraded in memory to the Campaign preset by `CampaignEngine.ensure_state`. The rules are persisted naturally on the next save-changing action.

## Future use

The same structure can support downloadable official rulesets or user-created rulesets later without requiring a traditional mod system. Rules files can also become a clean extension/data-pack mechanism while keeping core engine code stable.
