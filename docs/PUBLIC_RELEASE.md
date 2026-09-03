# Public Release Notes

This repository is prepared for public source review and Windows source-based installs.

## Included

- ElectionLab Python source code.
- Small bundled map runtime assets required by the current map renderer.
- Built-in starter candidate profile heuristics.
- 2024 ACS state-context snapshot with source metadata.
- Windows install, update and launcher scripts.
- Project documentation and self-test script.

## Excluded

- API keys and provider credentials. Each user must add their own optional OpenAI key in Settings.
- `portable_config.json`, because it can contain a local data-root path.
- `ElectionLabData/`, including saves, Knowledge Vault databases, portraits, logs, exports, research cache and local model folders.
- `.venv/`, pip caches and installer temp folders.
- Packaged release archives and generated executables. Those belong in GitHub Releases after a release build exists.
- Downloaded Wikipedia/Wikimedia portraits. The app can fetch optional portraits into the user's local data root and store source URLs there.
- Ollama model files. Users install Ollama and pull their own models separately.

## Data And Asset Provenance

The 2024 state-context data is derived from U.S. Census Bureau ACS tables listed in `electionlab/data/state_context_2024.json`. ElectionLab converts some official indicators into gameplay issue-priority heuristics; those derived values are not polling.

The U.S. map geometry is documented in `docs/MAP_SOURCE_NOTE.md` as a user-supplied SVG adapted for ElectionLab. The runtime raster files are generated from that geometry and are required by the current map renderer. Before a formal open-source release or third-party asset redistribution, confirm the original SVG's license/provenance or replace it with a clearly licensed map source and regenerate the runtime assets.

No commercial game assets, local AI model files, downloaded portraits or personal save data are included.

## License Status

No project license has been selected yet. Until a license is added by the repository owner, the code is public for review but not broadly open-source licensed for reuse.
