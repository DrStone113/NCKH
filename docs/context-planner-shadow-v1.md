# Context Planner v1 — D3.0 shadow mode

`context-plan-v1` is a deterministic, auditable preview of the minimum context,
tools, retrieval policy, and validators a future enforced router could use. In
D3.0 the existing turn router, memory/RAG load, prompt, model, tool schemas, and
response remain authoritative.

Enable development observation with `CONTEXT_PLANNER_MODE=shadow`. The only
accepted values are `off` and `shadow`; the default is `off`. There is no
enforced mode.

The planner uses `context-intent-v1`, the versioned source matrix and registry,
D1 status envelopes, and structural `ContextBundle` sections. It emits explicit
load, refresh, retry, conflict-resolution, or retrieval actions for unavailable
required data. A stale value is never represented as known. Required safety,
canonical numeric state, and evidence survive budget trimming; optional sources
are sorted by priority and source identifier before trimming.

Shadow traces contain source identifiers, status, estimated sizes, policies,
and latency. They do not contain raw bundle values. Planner output is not passed
to the production LLM or dispatcher. Planner failure is logged and the original
turn proceeds unchanged.

The 60-turn `context-planner-development-v1` corpus is synthetic and has
manually authored engineering oracle labels. It is separate from research A/B/C
and pilot/final benchmark material.

Known D3.0 limitation: the classifier is rule-based and intentionally falls
back to clarification/`SMALLTALK_OR_OTHER` outside strong rules. Live shadow
traffic review and adversarial evaluation are required before considering D3.1.
