# Server Semantic Routing

## Previous Architecture

The authenticated WebSocket chat entry point is `apps/backend/modules/chat/router.py`.
It creates `AgentOrchestrator` with the same backend-owned scope guard, tool
registry, dispatcher, and memory service for Flutter Web and mobile. The browser
does not load a model runtime.

The previous reachable sequence was: exact `PendingUserAction` claim, `ScopeGuard`,
Context Planner cost shadow, inference-tier router, then tool-schema selection.
`SemanticPrototypeScopeClassifier` and `StrictJSONScopeClassifier` classify scope,
not the product-level meal/menu/workout/Plan contract. `turn_intent.py` provides
Plan distinctions but is deterministic and the tool selector still has competing
keyword compatibility paths.

The isolated mobile S1 semantic router is telemetry-only. Its server boundary in
`services/agent/semantic_shadow.py` explicitly prevents client labels reaching
prompts, safety, tools, writes, or state.

## Stage-0 Evidence Map

| Current component | File / symbol | Current responsibility and callers | Problem found | Disposition |
| --- | --- | --- | --- | --- |
| Chat ingress | `modules/chat/router.py`, `/chat/stream` | Authenticated Flutter Web/mobile socket; creates orchestrator | No product semantic result spans later stages | Refactor caller only |
| Pending action | `pending_user_action.py` | Exact confirmation claim before normal routing | Correct priority; must remain independent of SLM | Keep |
| Scope/safety firewall | `scope_guard.py`, `ScopeGuard` | Orchestrator before history/RAG/tools | Scope labels are not product semantic contract | Keep; do not weaken |
| Embedding scope classifier | `semantic_scope_classifier.py` | Optional scope candidate classifier | Sentence-transformer prototypes are scope-only | Keep scope-only |
| Restricted JSON judge | `scope_guard.py`, `StrictJSONScopeClassifier` | Uncertain scope only | Schema cannot express portable product parse | Keep scope-only |
| Typed Plan intent rules | `turn_intent.py`, `TurnIntentDecision` | Plan/tool selection | Deterministic-only, not a server parse result | Refactor as cascade fallback |
| Tool selector | `orchestrator.py`, `_select_relevant_tool_schemas` | Narrows offered schemas | Competing keyword compatibility logic | Refactor to accept one decision |
| Context planner | `context_planner/` | Cost/context shadow | Maintains a separate classifier | Keep shadow behavior |
| Mobile S1 router | `apps/mobile/lib/services/semantic_router/` | Optional local parse and telemetry | Different vocabulary, non-authoritative | Keep as optional |
| Semantic shadow validator | `semantic_shadow.py` | Client telemetry boundary | Correctly untrusted | Keep |
| Local server runtime | `local_qwen_semantic_adapter.py`, `LocalQwenSemanticAdapter` | Existing narrow Transformers parser for a verified local checkpoint | Was not wired into server startup; existing Q8 GGUF is Android-only and incompatible with this adapter | Refactor and wire conditionally |

No frozen research artifact, nutrition/exercise policy, or model weight is
modified by this feature.

## Current Architecture

```text
authenticated Web/mobile request
  -> exact PendingUserAction claim
  -> ScopeGuard safety/scope firewall
  -> deterministic normalisation + typed candidate decision
  -> optional ServerSLMAdapter for uncertainty only
  -> deterministic semantic verifier
  -> ContextPlanner / tier router / tool policy / main LLM
```

The semantic result is never authority for identity, permissions, safety,
pending actions, tool execution, or writes. In `SHADOW`, it cannot change
context, tools, state, or user-visible output.

## Why Server-Side

The server already owns authenticated session state, durable pending actions,
safety routing, and tool policy. Server parsing makes Web and mobile consistent
without browser GGUF downloads, WebGPU/WASM requirements, or client authority.

## Semantic Contract

`SemanticParseResult` uses the established typed `TurnIntentDecision` fields
and adds bounded candidates, entities, references, ambiguity, parser/model
metadata, latency, and verifier status. Debug telemetry omits raw text and
entities. The existing mobile S1 result remains a compatible portable
observation shape, never an authority.

## Deterministic Cascade

Pending actions stay first and scope safety stays authoritative. Deterministic
typing supplies candidates and handles missing-model paths. The SLM runs only
for low confidence, clarification, or multi-candidate turns. A strict verifier
rejects malformed, unsupported, contradictory, or negated-write output and
falls back deterministically.

## SLM Invocation Policy

The adapter sees only current text plus a compact fixed JSON task. It has no
tools, profile, history, RAG, identity, pending-action data, or execution
capability. It emits one JSON object with bounded tokens; unavailable model
configuration does not fail chat routing.

## Model Provenance

The existing Android-only Q8 GGUF is recorded in `semantic_router_slm.md`, but
it cannot be loaded by the server's existing Transformers adapter. The server
target is the official `Qwen/Qwen3-0.6B` Transformers checkpoint, revision
`c1899de289a04d12100db370d81485cdf75e47ca`, Apache-2.0, whose published
`model.safetensors` SHA-256 is
`f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`.
It was downloaded on 2026-09-21 into ignored
`.models/Qwen3-0.6B-c1899de289a04d12100db370d81485cdf75e47ca`; the file is
1,503,300,328 bytes and its locally calculated SHA-256 matches the published
value. The Hub command later received `WinError 10013` while listing metadata,
but all model/tokenizer files had already arrived and were verified. Weights
remain outside Git and are checksum-verified before load.

## Server Runtime

For hosted OpenAI-compatible inference the adapter reuses `LLMClient`. For the
official local checkpoint it reuses the pre-existing `LocalQwenSemanticAdapter`
and Transformers; it adds no llama.cpp runtime or weights. Runtime load,
cold/warm latency, memory, malformed-output, and concurrency qualification are
partially measured. The original environment contained a CPU-only PyTorch
wheel; it was replaced in the backend virtual environment with the official
CUDA 13.2 PyTorch nightly `2.15.0.dev20260920+cu132`. It detects the local
RTX 5060 Ti (`sm_120`), and the adapter explicitly places the model on
`cuda:0`. GPU allocation after load is about 1.19 GB (peak reserved 1.31 GB).
The first strict parse in one process was 18,116 ms; a separate same-process
run measured 23,838 ms first turn and 2,157/2,151 ms subsequent warm turns.
All measured outputs passed strict JSON verification, but the model classified
the non-holdout smoke turns as `GENERAL_WELLNESS`, including turns intended to
exercise meal/workout semantics. Runtime is therefore real and usable in
shadow, while intent quality remains unqualified. The small sample is also
insufficient to report p95 or production concurrency capacity.

## Web Integration

Web continues normal authenticated `/chat/stream` messages. It receives no
model weight, native dependency, or authoritative semantic label. Server
shadow output is private diagnostic telemetry.

## Optional Mobile Path

The isolated mobile S1 candidate/normaliser/verifier/local-runtime work is
**KEEP_AS_OPTIONAL**. It remains telemetry-only and is not a Web/server gate.

## Shadow Mode

`SERVER_SEMANTIC_ROUTER_MODE=shadow` is default. Legacy execution remains
authoritative; the semantic result cannot affect tools, writes, context, safety,
state, or output. `off` disables it. `enforced` is a future explicit rollout
mode and must not be enabled before qualification.

## Development Dataset

Existing `tests/fixtures/turn_intent_development_v1.json` is debugging-only and
excluded from final qualification.

## Fresh Holdout

The fresh holdout and exclusion index live under
`tests/fixtures/server_semantic_routing_holdout_v1.*`. Its specification labels,
hash, distribution, freeze time and source state are recorded before scoring.
It was frozen at `2026-09-21T07:41:59Z` with 120 cases and SHA-256
`a2ccfa54b9c4872afff6ef9713bbd7422ee9872b65e665185f5ad8eca4da2810`.
The exact-normalised development/test exclusion index was empty. The source
worktree was already dirty (69 paths) at freeze, so this is recorded rather
than hidden or reset.

## Automated Oracle Protocol

Provenance is `AUTOMATED`: cases have deterministic specification labels. This
engineering track does not claim human review, labelling, adjudication, or kappa.

## A/B/C Design

The identical frozen holdout is evaluated as A (legacy), B (server cascade with
SLM disabled), and C (same cascade with a real server model). Missing model
makes C unavailable and leaves the A/B/C gate `NO`; mocks never count as C.

## A Results

Fresh frozen run: primary intent accuracy `0.5417`, health routing recall
`0.7857`, false ambiguity rate `0.0000`, false-positive write intent `0`, and
health safety-critical miss `2`. These results are diagnostic only and do not
meet readiness gates.

## B Results

Fresh frozen run: identical to A (primary intent accuracy `0.5417`, health
routing recall `0.7857`, false ambiguity rate `0.0000`, false-positive write
intent `0`, health safety-critical miss `2`). B correctly has no hidden SLM
improvement because it uses the deterministic fallback.

## C Results

The previous frozen holdout does not have a valid C score: before the local
runtime was repaired, one holdout utterance was used to diagnose a malformed
model response. Per the protocol, that makes it ineligible for a final A/B/C
comparison. A replacement holdout must be newly authored and frozen before a
full C run. The model is nevertheless real (not mocked): artifact verification,
load and strict JSON parse are recorded above.

## Incremental Value C-B

Not measured. Keep a critical-path SLM only if future C materially improves
difficult semantic categories while every hard gate remains zero.

## Health Routing

Health stays an overlay in `TurnIntentDecision`; meal/workout work is retained.
The semantic layer never diagnoses or overrides deterministic safety policy.

## Ambiguity

Ambiguity means missing domain/action, incompatible candidates, or unresolved
reference. Typo, no-diacritic and slang alone are not ambiguity.

## Negation

The verifier prohibits write intent when an action is negated. Write policy
independently authorizes every actual mutation.

## Multi-Intent

Secondary intents are ordered and bounded. Meal plus workout is not a combined
Plan unless planning semantics explicitly request both domains.

## PendingAction

Pending action resolution precedes semantic parsing. The SLM cannot infer or
execute targets; mixed confirmations continue normal routing.

## Hard Gates

False-positive write intent, pending target mutation, health-safety miss,
invalid verified result, and shadow behavior change must all equal zero before
readiness. Unit tests alone are insufficient.

## Web E2E

Authenticated real-Web E2E is blocked by a test-user session and a verified
server SLM artifact. Browser-only mocks do not count.

## Known Limitations

Scope and Context Planner still retain independent legacy classifiers. This
change supplies a reusable server result and removes Plan tool-selection
duplication; a qualified broader replacement requires frozen A/B/C evidence.

## Decision: Keep / Disable / Further Evaluate SLM

**Further Evaluate.** The strict adapter and shadow seam are useful, but no
approved model artifact or real C measurement exists.
