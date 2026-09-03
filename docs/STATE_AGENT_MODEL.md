# State-agent model — introduced in 0.6, current in 0.9

ElectionLab does **not** create 51 independent LLM sessions. Every state plus D.C. has a lightweight deterministic electorate state stored inside each campaign save.

The initial data context is stored in `electionlab/data/state_context_2024.json`. It includes state-level 2024 ACS indicators and source metadata. Current factual indicator inputs are median household income, median gross rent, and employment/unemployment. ElectionLab converts these into a small issue-priority layer for gameplay. The derived priorities are explicitly heuristic and are not represented as polling.

On each campaign turn, `StateAgentModel.apply_strategy` evaluates region + issue + tone against each targeted state's issue priorities. It stores cumulative movement, campaign attention, issue hits, and last touch by ticket. Repeating the same issue eventually produces diminishing returns.

The campaign Election Day simulation passes those state movements to the normal Monte Carlo election engine as state adjustments. AI is optional: it can narrate a constituent or explain a result, but it cannot silently replace the numerical state state or choose the election winner.
