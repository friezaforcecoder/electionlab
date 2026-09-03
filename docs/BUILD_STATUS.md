# ElectionLab 0.12 Build Status

## Working

- Traditional Main Menu / game shell transition
- New Game, Continue, load/manage saves and Quick Election flows
- Save-local official rules presets + customized rules
- Arcade / Campaign / Simulation / Analytical / Forecast Lab campaign presets
- Persistent campaign saves, branching, visible seeds and deterministic replay contract
- 538-EV Monte Carlo election engine
- Geographic 51-jurisdiction map with fast raster hit testing and repaired composited visuals
- Knowledge Vault with 95 built-in starter profiles, custom profiles, deletion/tombstones and safe seed-pack upgrades
- Online profile research/provider fallbacks and local-AI enrichment hooks
- Staged visible Research + Cache worker progress and staged manual AI narration progress
- Candidate/VP portraits and cached portrait workflows
- Campaign timeline/calendar, debate takeovers, Instant Election handling
- Live state-agent electorate, State Operations, Campaign Operations, simulated polling, War Room and campaign map
- Campaign Operations Center for fundraising, endorsements, media buys, field surges and rapid response actions
- Campaign Conversations / AI debate interaction when a provider is available
- Data workspace and 2024 ACS starter state context
- Per-session diagnostics (`latest_session.log`)
- Simulation Archive and result intelligence
- Hidden-window Windows launcher path through `Run_ElectionLab_NoConsole.vbs` / `ElectionLab.pyw`

## Important limitations before 1.0

- Main Menu is new, but Campaign gameplay still uses the existing large Campaign HQ layout internally; future builds will increasingly reshape this into a more game-like in-campaign HUD/section system.
- Real/live polling, current-event ingestion, sourced state issue polling, live approval/favorability and current economic feeds are not implemented yet.
- Maine/Nebraska district allocation remains planned.
- Primaries/conventions/VP search remain planned.
- AI providers are optional and do not determine the numerical election winner.
- Batch/VBS launcher and installer files remain transition plumbing; native packaged Windows app is still the release target.

## 0.12 validation

The core self-test covers 95 profiles, 538 electoral votes, 51 map jurisdictions, deterministic instant elections, deterministic campaign replay, state-agent movement, State Operations, Campaign Operations, polling, diagnostics, OpenAI model normalization, safe profile seed updates, simulation archive behavior and save-local rules/preset enforcement.
