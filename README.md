# ElectionLab — Pre-1.0 Build 0.12

ElectionLab is a local-first U.S. presidential election / campaign sandbox. Build 0.12 continues the transition from a desktop-utility shell to a traditional campaign game while preserving the existing election engine, Knowledge Vault, geographic map, state agents, campaign saves, AI providers, rulesets, diagnostics, and data workspace.

## Quick start on Windows

1. Install Python 3.11 or newer.
2. Clone or download this repository.
3. Run `Install_ElectionLab.bat`.
4. Choose a data folder when prompted, or press Enter to use the default `ElectionLabData` folder beside the app.
5. Launch with `Run_ElectionLab_NoConsole.vbs`.

ElectionLab's election and campaign systems run without OpenAI or Ollama. OpenAI, Ollama, web research and portrait fetching are optional layers for research, narration, dialogue and enrichment.

Developer run path:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m electionlab
```

Run the core validation suite:

```powershell
.\.venv\Scripts\python.exe scripts\core_self_test.py
```

## 0.12 headline: campaign operations release

0.12 adds a new **Operations Center** to Campaign HQ. Campaigns can now spend or raise resources through deterministic, save-local operations:

- **Fundraising Drive** — raises campaign funds with modest momentum and state effects.
- **Endorsement Push** — converts political support into momentum and targeted state movement.
- **Media Buy** — spends more aggressively for stronger regional or national persuasion.
- **Field Surge** — invests in turnout/ground-game strength and state movement.
- **Rapid Response** — answers events or pressure with low-cost momentum and regional effects.

Operations use the existing campaign rules, strategy regions, message/tone system, state agents, campaign funds and timeline. They are computed locally by the campaign engine; optional AI can narrate or contextualize the campaign, but it does not decide numerical results.

The map keeps the 0.11.1 canonical compositor but removes the opaque hover/selected-state fill. Hover and selection now use outline/glow edges only, leaving the state's actual election color visible. The election palette is also slightly darker and more saturated.

OpenAI model IDs are normalized consistently before storage and provider use, so a value such as `GPT-5.4-mini` becomes `gpt-5.4-mini` everywhere.

Launching without a visible terminal window is now the intended Windows path. Use `Run_ElectionLab_NoConsole.vbs` for the hidden-window launcher; `Run_ElectionLab.bat` remains as a compatibility launcher that starts `ElectionLab.pyw` through `pythonw.exe`.

## 0.11.1 hotfix: canonical map compositor

0.11.1 replaces the stitched visible map with one canonical full-canvas jurisdiction index generated directly from the original SVG. State colors are applied by changing an 8-bit palette, then one national border layer is drawn on top. This removes cropped-state seams, drift and clipping while preserving single-pixel hit testing.

The old 51-tile runtime compositor is removed. The same canonical index image is used for both coloring and hit detection, so what you see and what you click share exactly the same geometry. The new map assets are also shared/lazy enough to reduce the expensive map work that previously happened during GUI construction.

Main Menu now renders **Data & Sources** correctly; the ampersand is escaped so Qt no longer displays the mnemonic-underlined space as an underscore.

## 0.11 headline: the game shell

ElectionLab now launches into a **Main Menu** rather than a permanent feature sidebar.

- **Continue Campaign** — resumes the active/latest save.
- **New Game** — creates a campaign using an official rules preset or customized rules.
- **Load / Manage Campaigns** — opens the save library and timeline tools.
- **Quick Election** — keeps the instant matchup / Monte Carlo simulator as a standalone mode.
- **Knowledge Vault** — candidate/person profiles and portraits.
- **Data & Sources** — model inputs and provenance.
- **Settings** — installation/provider settings only.
- **Exit** — closes ElectionLab.

When you enter Campaign gameplay, you are inside that campaign rather than navigating a global app sidebar. A compact top bar returns to the Main Menu.

## Official campaign rules presets

Every new campaign stores its rules inside the save file. Official presets are templates; changing a rule marks the save as **Modified** without changing the original preset.

- **Arcade** — faster, more dramatic campaign effects.
- **Campaign** — balanced intended game experience.
- **Simulation** — observer-oriented AI-vs-AI campaign.
- **Analytical** — more restrained campaign movement and stronger fundamentals.
- **Forecast Lab** — maximum transparency/uncertainty with conservative campaign effects.

The New Game screen exposes campaign, electorate, AI, and data rules. Future sourced live-data modules are already reserved in the save schema but remain disabled until they actually exist; ElectionLab does not silently fabricate them.

Rules stored per save currently include debates, State Operations, simulation polling, Campaign Conversations, campaign resources, random events, fundraising/endorsement event systems, AI narration, state priorities, historical baselines, demographics/economics/turnout context, candidate traits, AI dialogue/opponents/state explanations, uncertainty, campaign-effect strength, and Monte Carlo depth.

Existing pre-0.11 campaigns migrate safely to the balanced **Campaign** preset.

## Research + AI job reliability

Knowledge Vault research now runs as an explicit staged background job:

1. validate settings,
2. try OpenAI web research when enabled,
3. try public web + local AI if applicable,
4. try a conservative public-web fallback,
5. validate/save the profile,
6. report completion.

The loading overlay and Knowledge Vault status line update as the job moves through these stages, and every stage is written to `latest_session.log`.

If the Add Person field is empty, **Research + Cache** and **Local AI Enrich** now operate on the currently selected Knowledge Vault profile rather than silently doing nothing.

Manual Campaign History narration also uses a staged background job with visible progress and diagnostic events.

OpenAI support uses the Responses API. Model IDs are normalized to lowercase before storage and provider use; a manually selected model ID is preserved in normalized form.

## Geographic map visual repair

The fast raster hit-map from 0.9/0.10 is retained for interaction, but state fills are no longer independently scaled into the window. Build 0.11 composes all 51 jurisdiction masks at their original shared map resolution, draws the border layer once, then scales the completed map as a single image.

That keeps the fast single-pixel state hit testing while removing the gaps/overlaps that made recent map builds look visually broken.

## Local-first behavior

Election calculations do **not** require OpenAI or Ollama. The numerical election/campaign engine remains local and deterministic. AI is an optional interpretation/dialogue/research layer.

Large mutable data can remain on another drive via the selected ElectionLab data root:

- Knowledge Vault and portraits
- campaign saves
- simulation archive
- research cache
- data packs
- AI models
- logs

No xAI/Grok/X integration exists.

## Public repo safety

This repository intentionally excludes `portable_config.json`, `ElectionLabData/`, saves, Knowledge Vault databases, cached portraits, logs, research cache, local model files, virtual environments, installer caches, packaged zips and generated executables. Optional OpenAI keys must be supplied by each user and are stored through the operating system credential service, not in source files.

See `docs/PUBLIC_RELEASE.md` for the public release checklist, excluded/private data list and asset/data provenance notes.

No project license has been selected yet. Until the repository owner adds one, the code is public for review but is not broadly open-source licensed for reuse.

## Install / update

For a new install, extract ElectionLab to the drive you want and run `Install_ElectionLab.bat`.

For an existing install (0.10, 0.11 or 0.11.1):

1. Close ElectionLab.
2. Extract the 0.12 ZIP somewhere temporary.
3. Run `Update_Existing_Install.bat` from the extracted 0.12 folder.
4. Point it at your existing ElectionLab folder.
5. Launch with `Run_ElectionLab_NoConsole.vbs` for the normal hidden-window path.

Your `portable_config.json`, selected external data root, `.venv`, Knowledge Vault, portraits, custom/researched profiles, campaign saves and simulation archive are preserved.

BAT launch/install files remain compatibility plumbing. The release target is still a normal installed `ElectionLab.exe` / Start Menu shortcut with no terminal window, while large models and mutable data remain wherever the user selected.

## Validation

`Core_Self_Test.bat` covers 95 built-in profiles, 538 electoral votes, all 51 map jurisdictions, deterministic election/campaign seeds, state-agent campaign movement, State Operations, Campaign Operations, simulated polling, diagnostics, OpenAI model normalization, profile seed migration, simulation archive behavior, and save-local rules/preset behavior.
