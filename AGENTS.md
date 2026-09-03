# ElectionLab Agent Notes

ElectionLab is a local-first U.S. presidential election and campaign simulation game.

## Non-negotiables

- Never commit API keys, credentials, local machine paths, personal saves, Knowledge Vault databases, portraits, logs, model files, virtual environments, packaged releases or generated caches.
- Keep election and campaign math deterministic and inspectable. AI may research, narrate, explain or roleplay, but it must not directly decide numerical winners or mutate core results outside explicit deterministic engine systems.
- Preserve existing user data during install/update flows: `portable_config.json`, `ElectionLabData/`, `KnowledgeVault/`, `Campaigns/`, `Saves/`, `ResearchCache/`, `Models/`, `DataPacks/`, `Extensions/`, `Exports/` and `Logs/`.
- Treat built-in profile scores and issue priorities as gameplay heuristics. Do not present them as objective ratings, polling or factual claims.
- Keep remote providers optional. The app must run without OpenAI or Ollama for local election/campaign simulation.

## Before Opening A PR

- Run `python -m compileall app.py electionlab scripts`.
- Run `python scripts/core_self_test.py`.
- Run a secret/privacy scan for keys, tokens, local paths, logs, databases, saves and generated artifacts.
- Check public release notes whenever adding assets or sourced data.
