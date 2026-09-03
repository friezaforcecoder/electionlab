# ElectionLab changelog

## 0.12 — Campaign operations, map interaction polish, model normalization

### Campaign gameplay
- Added the Campaign HQ Operations Center with Fundraising Drive, Endorsement Push, Media Buy, Field Surge and Rapid Response actions.
- Operations consume or raise campaign funds, write campaign timeline events, apply region/message/tone strategy and update state-agent effects deterministically.
- Added save-local rules for Media buys, Field surges and Rapid response so older saves inherit new Campaign defaults without losing existing rule overrides.
- Election Day now reads save-local campaign rules for fundamentals, candidate traits, debates, uncertainty, Monte Carlo depth and simulation mode.

### Map and UI
- Removed opaque hover/selected-state fills from the campaign and election map.
- Replaced hover/selection fills with outline/glow edge rendering so the underlying state color remains visible.
- Darkened and saturated the map result palette while keeping the 0.11.1 canonical compositor.
- Updated the Main Menu build label for the campaign operations release.

### Launching and compatibility
- Added `ElectionLab.pyw` and `Run_ElectionLab_NoConsole.vbs` for hidden-window Windows launching.
- Updated `Run_ElectionLab.bat` to start `ElectionLab.pyw` through `pythonw.exe` and exit instead of leaving a command window open.
- Added `Update_Existing_Install.bat` to copy application/runtime files while preserving `.venv`, `ElectionLabData`, `portable_config.json`, saves, profiles, portraits, logs, data packs and settings.

### AI/provider handling
- Added centralized OpenAI model ID normalization.
- Settings load/update and OpenAI provider construction now normalize values such as `GPT-5.4-mini` to `gpt-5.4-mini`.
- AI remains optional narration/dialogue/research; it does not decide computed election or campaign results.

### Tests
- Expanded core self-test coverage for Campaign Operations, rule merging for older saves and OpenAI model normalization.

## 0.11.1 — Canonical map compositor hotfix
- Rebuilt map runtime assets directly from the original SVG on one shared 1028×746 canvas.
- Replaced visible 51-state tile stitching with one indexed national raster whose palette is recolored per result/turn.
- Uses the exact same canonical jurisdiction index for hit testing, eliminating visual/click geometry disagreement.
- Added clean full-map border raster and regenerated compact hover/selection masks with padding to prevent clipped edges.
- Removed the obsolete 0.9–0.11 cropped raster asset pack from the distribution.
- Reduced map initialization/rebuild work by sharing canonical assets and recoloring a palette instead of loading/tinting 51 state images for every map instance.
- Fixed the Main Menu `Data & Sources` button displaying as `Data_Sources` because Qt interpreted the ampersand as a mnemonic marker.
- Updated diagnostics/build labels to 0.11.1 and expanded self-test coverage for the canonical indexed map.

## 0.11 — Game shell, campaign rulesets, map visual repair, staged AI jobs

### Game structure
- Replaced the permanent desktop-style sidebar as the primary navigation model with a traditional Main Menu.
- Added Continue Campaign, New Game, Load / Manage Campaigns, Quick Election, Knowledge Vault, Data & Sources, Settings and Exit menu actions.
- Added a compact in-mode top bar with Main Menu return instead of a global feature sidebar.
- Quick Election remains a standalone simulation mode; campaign gameplay remains persistent and save-based.

### Save-local rule system
- Added official Arcade, Campaign, Simulation, Analytical and Forecast Lab campaign presets.
- Added per-campaign rule storage and a New Game rule editor.
- Editing a preset marks that campaign `Modified`; official preset templates are not mutated.
- Rules now travel with portable campaign saves and are independent from installation/provider Settings.
- Existing campaigns migrate to the balanced Campaign preset.
- Debates, simulation polling, State Operations, resource costs, random campaign events and state-priority campaign effects now honor relevant campaign rules.
- Campaign-effect-strength is stored per preset and scales new state movement while preserving prior history.

### Knowledge Vault / AI jobs
- Research + Cache is now a staged ProgressThread job with visible loading progress and diagnostic stage events.
- Empty research field falls back to the selected saved profile instead of silently returning.
- Local AI Enrich gets the same selected-profile fallback and visible worker progress.
- Manual campaign narration now exposes staged progress instead of appearing idle during the provider request.
- Research provider stages are recorded in `latest_session.log`.

### Map
- Retained the fast raster hit map and prebuilt masks.
- Fixed visual seams/gaps caused by scaling each cropped state raster separately.
- All jurisdictions are now composited at the common 1028×746 source resolution before the completed map is scaled to the widget.

### UI / compatibility
- Campaign save library now shows rules preset / modified state.
- Campaign header displays the active ruleset and seed.
- New games proceed directly into campaign gameplay after creation.
- Campaign deletion refreshes Main Menu continue state.
- Added 0.11 game-shell QSS styling.

### Tests
- Added ruleset deep-copy/modified-state checks.
- Added disabled-debate, disabled-polling and resource-disabled campaign tests.
- Existing deterministic simulation/campaign, map, diagnostics, profile migration and State Operations tests continue to pass.
