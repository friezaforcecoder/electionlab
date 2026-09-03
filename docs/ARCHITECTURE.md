# ElectionLab architecture notes — 0.12

## Core rule
AI is an interpretation/interaction layer, not the authority that directly picks election winners. Numerical election/campaign state remains local, inspectable, deterministic where seeded, and serializable.

## Boundaries

1. **Knowledge Vault** — persistent candidate profiles, source metadata, simulation inputs and cached portraits.
2. **Election Engine** — deterministic/Monte-Carlo state calculations; no network calls.
3. **Campaign Engine** — date/turn/strategy/momentum/event ledger; no network calls.
4. **State-Agent Layer** — 51 lightweight persistent numerical electorate states. Strategy changes these agents; LLMs do not control their numbers.
5. **Data Layer** — sourced state/context snapshots + provenance. Derived ElectionLab issue priorities are explicitly separated from sourced facts.
6. **Provider Layer** — optional OpenAI, local Ollama, conservative public-web profile lookup, portrait cache and AI campaign/debate/narration interaction.
7. **Campaign HQ** — gameplay orchestration over a selected portable campaign save, including live state map, conversations and scheduled major-event takeover.
8. **UI** — desktop application; provider and persistence logic stay behind service boundaries.
9. **Extension Layer** — pre-1.0 reads manifests/data packs only. Arbitrary executable plugin code is intentionally not auto-loaded yet.

## Provider flow

Profile research:

`OpenAI + web (if enabled) -> public web reference + local AI -> conservative web-only profile`

AI campaign interactions:

`Auto (local first) -> Local Ollama -> OpenAI fallback when permitted`

Campaign-history narration:

`deterministic turn first -> optional Local/OpenAI narration afterward`

Narration never changes the computed turn. Re-generating the prose must not alter the seed universe.

Offline Lock blocks every remote path, including OpenAI, web profile lookup and portrait downloads. Local Ollama is permitted only over the configured loopback/local endpoint.

## Map rendering

The user-provided state SVG is preprocessed into a canonical indexed raster, per-state masks and a full-map border layer. Runtime map widgets recolor the indexed raster palette, draw the border layer once, and use the same state index for hit testing.

Hover and selected-state feedback is painted as edge-only outline/glow overlays derived from state masks. The underlying state fill is not covered by translucent interaction layers.

This preserves state-level interaction without embedding a browser/WebEngine runtime.

## Data workspace

The Data page is not an alternate source of truth; it exposes what the simulation has loaded. Each data pack should carry:
- source/provenance,
- snapshot/retrieval date,
- field definitions,
- confidence/status,
- separation between observed/source values and ElectionLab-derived heuristics.

The current first pack contains ACS 2024 state fundamentals. Future live-data modules should plug into this layer rather than directly mutating UI or election code.

## Persistent deletion
Knowledge Vault deletes create profile tombstones. This prevents a user-deleted built-in profile from silently reappearing during a future starter-data seed refresh. Explicitly adding/researching that person again clears the tombstone.

## Extension/update direction
A future updater can deliver signed first-party modules/data packs into the external data root. This is preferable to making every future feature a monolithic reinstall and still leaves a controlled modding path if it becomes useful.

Potential module types:
- election model versions
- primaries/conventions
- richer debate/event schedules
- fundraising/advertising/field operations
- election-night reporting
- historical election environments
- state/county polling and demographic data packs
- candidate packs
- UI panels
- congressional/international election engines

Save files carry `schema_version` so migrations can preserve older campaigns.

## Windows packaging target
Release builds should package the Python/PySide runtime with ElectionLab and launch through a normal GUI executable with no console window. End users should not need Python, a virtual environment, batch files or a terminal. The immutable application runtime and mutable `ElectionLabData` root remain separate so large AI models/caches can live on D:/F:/etc.

## 0.8 responsiveness and interaction layer

Long-running election work now follows: UI snapshot → worker thread → progress signals → immutable numerical result → main-thread render. The election engine accepts an optional progress callback but its seeded RNG and mathematical result are unchanged.

Geographic mouse interaction is separated from geographic rendering. The detailed SVG/QPainterPath geometry is still rendered visually, but the map builds an invisible per-state RGB hit raster on layout. Mouse hover/click reads one pixel from that raster, eliminating live `QPainterPath.contains()` calls against complex coastlines.

Saved instant-election results are handled by `SimulationArchive` and live under `Saves/Simulations` in the selected data root. They are plain portable JSON and do not depend on the application install path.

## 0.10 diagnostics + raster runtime layer
- `SessionDiagnostics` owns `<data root>/Logs/latest_session.log` and truncates it at launch.
- Main-window UI heartbeat detects recovered event-loop stalls and records the active action marker.
- Campaign HQ refreshes are deferred when the page is hidden; opening HQ paints the destination before refresh work begins.
- Active campaign objects are cached in memory during gameplay so map-state inspection does not reread save files.
- Geographic SVG geometry is pre-rasterized into per-state masks and a hit-ID image; no detailed vector geometry is required for runtime map interaction.
- State Operations and simulated polling remain deterministic core-engine systems. AI may narrate/explain them later but does not generate their numerical effects.

## 0.11 game-shell boundary

The UI now has two conceptual layers:

1. **Main Menu** — choose New Game, Continue, Quick Election or utility workspaces.
2. **Mode shell** — a compact top bar plus the active internal screen. Campaign gameplay is treated as a game mode, not a peer of Settings/Data/Knowledge Vault in a permanent sidebar.

The existing feature-page widgets are deliberately retained during the transition so 0.11 changes navigation architecture without rewriting the election/campaign engines at the same time.

Campaign behavior is no longer inferred from global Settings. `core/rules.py` defines official ruleset templates; a deep copy is stored in each campaign save. This is also the planned boundary for future shareable rulesets/data-pack-driven game variants.

## 0.12 campaign operations boundary

Campaign Operations are deterministic engine actions layered on the existing campaign rules and state-agent systems. They can spend or raise funds, move momentum, adjust field strength and apply regional state effects, then append a timeline event to the campaign save.

AI providers may narrate or contextualize operations later, but operation legality and numerical effects are resolved by local campaign-engine code. Existing saves merge in newly introduced campaign rule defaults rather than replacing user-customized rule choices.
