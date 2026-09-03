# Candidate starter data packs — 0.10

ElectionLab separates **starter-owned** candidate data from **user/research-owned** data.

## EL Starter Enrichment v2

0.10 replaces many neutral `50/100` starter placeholders with varied offline game-model inputs for all 45 U.S. presidents and the 50 bundled public figures.

These numerical traits are ElectionLab simulation heuristics, not objective judgments. The starter pack deliberately does **not** invent issue positions merely to fill fields. Unknown positions remain unknown until a sourced research path or explicit user edit supplies them.

## Safe merge rule

When a new starter pack is installed, ElectionLab may update an existing record only when all of the following are true:

- `source_type` is still `built_in`;
- `profile_status` still begins with `starter`;
- the profile is not locked;
- the user has not deleted/tombstoned it.

Profiles created by the user or enriched through web/OpenAI/local AI are not replaced by starter updates. Existing portrait paths are also preserved.
