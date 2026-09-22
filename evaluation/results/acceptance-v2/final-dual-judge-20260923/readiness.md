# Final dual-judge preflight

The proposed final set contains 55 existing answer records. The versioned source precedence is recorded in `final_input_manifest.json`; its case IDs match the existing frozen 55-case outcome oracle. No answer generation was rerun and no frozen inputs were edited.

## Fixed configuration

- Judge A: `cnb/grok-4.5`
- Judge B: `vc/qwen3.8-max`
- Blind adjudicator: `zc/glm-5.3-flash`, only for dimensions on which A and B disagree
- Temperature: 0 for all three
- Frozen rubric SHA-256: `d58339311bf1218a39fa9a80c7592e4b2be906ee261374082426af5bd0c79deb`
- Same case query, captured tool evidence with provenance metadata, and final answer for all judges. Historical grades, expected answers, failure labels, and other judges' outputs are excluded from prompts.

## Current gate

Fresh probes of Grok and Qwen returned valid structured JSON. The GLM route is listed as active; its first probe and first cooldown retry returned upstream HTTP 429, but a later spaced retry returned valid structured JSON with the same frozen rubric. All three valid probe results are recorded in `preflight.json`, with the earlier GLM failure retained. The provider returned no quota or rate-limit allowance headers. Read-only `/v1/usage`, `/v1/balance`, and `/v1/credits` requests returned 404.

Provider balance and quota are operational concerns. The runner records transport and structured-output failures, backs off, and resumes from valid checkpoints without rejudging completed cases.

Readiness requires the frozen 55-case manifest and rubric to match and all three named routes to have valid recent structured-output probes. The existing MiniMax artifacts are historical and were not modified.
