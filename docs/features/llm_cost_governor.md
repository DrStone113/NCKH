# LLM cost governor

The backend now treats paid inference as a per-turn budget instead of an
unbounded side effect of the ReAct loop. The feature is enabled by default with
`LLM_COST_OPTIMIZATION_MODE=optimized`; `off` exists only as a scoped rollback
and comparison switch.

## What is enforced

| Turn tier | Prompt | Paid-call ceiling | Output ceiling | Raw history ceiling |
|---|---:|---:|---:|---:|
| Chitchat | light | 1 | 160 tokens | 0 turns |
| Simple | compact | 2 | 512 tokens/call | 6 turns |
| Complex | compact | 3 | 1,200 tokens/call | 12 turns |

The ceiling includes the final synthesis call. When the budget is exhausted,
the orchestrator returns a deterministic recovery message instead of quietly
buying another completion. Cross-model fallback and same-model retries are off
by default. Provider `401` and `402` responses remain terminal.

The compact prompt keeps the safety, allergy/restriction, consent, privacy,
planned-versus-completed, tool fidelity, medical, and canonical-data rules. It
selects only the policy blocks and tool schemas relevant to the current turn.
For a representative nutrition/plan catalog in the focused development check,
the static system prompt fell from 30,258 to 3,098 characters (about 7,565 to
775 tokens using the conservative character/4 estimate), or 10.2% of the old
size. This is a prompt measurement, not a provider invoice or production KPI.

## Avoided calls

- Chitchat sends no tools and no chat history.
- High-confidence deterministic context policy can skip RAG and contextual FTS
  when they are forbidden for the intent. Uncertain routing keeps the prior
  fail-open context path.
- Authoritative typed plan, workout, and nutrition presentations are returned
  directly; they do not pay for a second prose rewrite that would be discarded.
- Rolling summary and fact extraction are deduplicated per session, run only
  after a configurable number of new turns, and have independent output caps.
- Provider/model fan-out is opt-in rather than implicit.

No shared response cache is introduced. Health/profile/chat content is
owner-scoped and may be time-sensitive; cross-user caching would create privacy
and freshness risks. Deterministic typed renderers are the safe reuse boundary.

## Configuration

```dotenv
LLM_COST_OPTIMIZATION_MODE=optimized
LLM_CROSS_MODEL_FALLBACK=false
LLM_ATTEMPTS_PER_MODEL=1
LLM_CHITCHAT_MAX_OUTPUT_TOKENS=160
LLM_SIMPLE_MAX_OUTPUT_TOKENS=512
LLM_COMPLEX_MAX_OUTPUT_TOKENS=1200
LLM_SIMPLE_MAX_CALLS=2
LLM_COMPLEX_MAX_CALLS=3
LLM_SIMPLE_HISTORY_TURNS=6
LLM_COMPLEX_HISTORY_TURNS=12
LLM_MEMORY_SUMMARY_MAX_OUTPUT_TOKENS=512
LLM_MEMORY_FACT_MAX_OUTPUT_TOKENS=512
SUMMARY_MIN_NEW_TURNS=12
```

Debug traces include `TURN_BUDGET_ASSIGNED` with the tier limits and a
dependency-free input-token estimate. This payload contains counts and policy
settings, not prompt text, profile values, API keys, or provider response
bodies.

## Qualification boundary

Focused unit tests establish structural ceilings and deterministic behavior.
They do not establish production savings, response-quality parity, calibrated
SLM confidence, or final rollout readiness. Before changing the defaults in a
deployed environment, compare real provider usage and a human-labelled
Vietnamese holdout while keeping safety behavior deterministic.
