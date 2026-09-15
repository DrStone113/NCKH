# SEMANTIC ROUTER S1 ONE-SHOT REPORT

Status: implementation and Android installation complete; model-enabled shadow is not qualified on LDPlayer.

## 1. Codespace Audit

- Flutter uses `provider`/`ChangeNotifier`; `AIChatProvider.sendMessage` owns the authenticated WebSocket path. Navigation is `MaterialApp` plus `Navigator`.
- Android contains duplicate Groovy/Kotlin Gradle files; Gradle actually selects the Groovy build files. The active app build now targets Java 17. There is no iOS project. Web remains supported.
- Qualification used the project SDK: Flutter 3.44.8 / Dart 3.12.2. The global PATH SDK was not used.
- Backend flow is `ChatGateway` FIFO -> `AgentOrchestrator` -> deterministic safety/scope -> context/router -> policy/tool/LLM. The exact pending write target exists only in `PendingUserActionStore`.
- Context Planner `context-intent-v1` has 14 supported intents. Safety, allergy, ownership, source/tool policy, confirmation, persistence and freshness stay backend-authoritative.
- The model cache was initially empty. An official checksum-pinned Qwen Q8 artifact was later installed outside the repository; no weight was committed.
- LDPlayer 9 was detected at `emulator-5554`, Android 9/API 28, x86_64 with Houdini ARM translation. A complete user-scoped Android toolchain was installed and the normal app was built, installed and launched.
- Research, D3, Plan freeze, canonical nutrition and exercise boundaries were inspected before S1. The worktree already contained extensive unrelated changes and five pre-existing P2.1R source-hash mismatches.

## 2. Existing Routing Architecture

```text
Flutter UI -> AIChatProvider -> authenticated WebSocket -> ChatGateway FIFO
  -> backend safety/scope -> context/turn router -> policy/tool/RAG/LLM -> validators
```

S1 adds an observation-only side path:

```text
raw message -> conservative normalizer -> cheap candidate router
  -> pending/high-confidence early exit OR optional local SLM
  -> strict parser -> deterministic verifier -> sanitized semantic_shadow event
```

The original chat request is sent first and unchanged. It remains the only user message used by production behavior.

## 3. Failure Modes Found

- Existing lexical classification misses teencode, typos, slang, regional wording and many short references.
- Single-label scoring loses secondary intent and can convert genuine ambiguity into `SMALLTALK_OR_OTHER`.
- Existing deterministic write cues produced two false-positive writes on negated requests in the DEVELOPMENT set.
- Pending confirmation was exact but was resolved after general scope/context work, allowing unrelated interpretation to run first.
- The safety sentence `Tôi ngất sau khi chạy bộ` was classified as fitness rather than safety because the unaccented standalone cue was missing.

## 4. Implementation Plan

1. Record the current architecture/frozen boundaries and create a separate `SYNTHETIC_DEVELOPMENT` set.
2. Implement immutable contracts, conservative normalization, candidate routing, optional local SLM, strict parsing and deterministic verification.
3. Integrate one Android GGUF runtime behind conditional imports; unsupported platforms fail safely.
4. Send shadow observations separately and never merge client hints into production context/routing.
5. Make exact pending resolution the first backend decision and retain hard safety as deterministic authority.
6. Run focused/full Flutter and backend tests, baseline/evaluation scripts, web build and frozen checks.

Rollback remains configuration-only with `SEMANTIC_ROUTER_MODE=off`; SLM output has no production authority.

## 5. Actual Implementation

- Added the isolated Dart module under `lib/services/semantic_router/`: contract, text normalizer, candidate router, verifier, cascade and conditional runtime.
- Added `llama_flutter_android 0.2.6` plus `crypto`, raised Android `minSdk` to 26 as required by the plugin, and added release native keep rules.
- Added optional dependency injection to `AIChatProvider`, a per-turn ID, pending-state tracking and asynchronous shadow observation after the original request is sent.
- Added backend `semantic_shadow` schema validation and a gateway branch outside the chat FIFO. The branch can emit authenticated developer telemetry but cannot invoke the orchestrator.
- Moved exact pending-action claim/resolve/reject ahead of scope, context and LLM work. Added the missing deterministic `ngat` safety cue.
- Added mobile/backend unit tests, a 50-case DEVELOPMENT dataset, legacy baseline evaluator, no-model cascade evaluator and LDPlayer benchmark runner.
- Installed Microsoft OpenJDK 17.0.20.1, Android command-line tools 22.0, Platform/Build Tools 36, Platform Tools 37.0.1, NDK 27/28.2 and CMake 3.22.1. Flutter doctor reports the Android toolchain and licenses green.
- Corrected the active Groovy Android build (the repository contains both Groovy and inactive Kotlin DSL files): Java 17, minSdk 26, release native keep rules and optional Google Services application when a real `google-services.json` exists.
- Added native timeout poisoning/settlement guards so a timed-out generation cannot be reused or freed while its native call may still be live.

## 6. Mobile Inference Runtime Selected

Selected: llama.cpp/GGUF through `llama_flutter_android`, isolated behind `SemanticSlmRuntime`. ONNX Runtime has an official Qwen3 Android example, but would require a custom tokenizer/generation bridge and multi-file delivery in this repository. No second inference stack was added.

The selected Flutter package is Android-only, ARM64-oriented, requires API 26/NDK/CMake, and is published by an unverified pub.dev uploader. Those facts make it suitable for a shadow integration experiment, not a production supply-chain approval.

## 7. Model Selected

Contract target: `Qwen/Qwen3-0.6B-GGUF`, Apache-2.0, language-only, `/no_think`, strict compact JSON, no tools and no policy authority. The official repository provides GGUF releases including Q8; an approved Q4 artifact/source has not yet been selected.

## 8. Quantization

The executed device experiment used the only GGUF in the official Qwen repository: `Q8_0`, 639,446,688 bytes. Q4 was not downloaded because no first-party Q4 artifact was available. There is no Q4-vs-Q8 quality claim.

## 9. Model Delivery / Storage

Weights are not committed or bundled. The official `Qwen3-0.6B-Q8_0.gguf` is stored at `%LOCALAPPDATA%\NCKH\Models` and was verified against Hugging Face LFS SHA-256 `9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031`. The benchmark copied it to app-private Android storage. Android builds accept model path, ID, quantization and expected hash as compile-time values; the runtime verifies file existence and SHA-256 before load. Missing/wrong/unsupported inputs yield typed fallback.

## 10. SemanticParseResult Contract

`semantic-router-s1-v1` preserves raw text on device and exposes normalized candidates, primary/secondary intent, scored candidates, typed entities/slots, write intent/action, negated actions, confirmation, reference kinds, ambiguity/clarification, parser/model versions, latency, verifier state and uncertainty. Wire enums are allowlisted and immutable. `toTelemetryJson` removes raw text, normalized text, entities and slots; only safe aggregate metadata and the model hash may leave the device.

## 11. Cascade Strategy

Order: normalize -> candidate classification -> pending authoritative bypass -> deterministic high-confidence early exit -> runtime availability -> one SLM parse -> strict JSON validation -> deterministic verifier -> candidate fallback. On 50 DEVELOPMENT cases with no model: 16 deterministic high-confidence exits, 30 `MODEL_UNAVAILABLE` fallbacks and 4 pending authoritative exits.

## 12. Normalization

Raw text is never overwritten. Normalization removes zero-width controls and collapses whitespace. Only unambiguous token rewrites such as `j -> gì`, `dc/đc -> được`, `mún -> muốn`, `hok/hông -> không` may form the preferred candidate. Ambiguous `k/ko -> không` and repeated-character reduction remain separate candidate transforms with explicit reason codes.

## 13. PendingAction Priority

Mobile bypasses the SLM while a compatible pending action is active. Backend now claims and resolves/rejects `PendingUserAction` before scope, context, semantic classification or LLM work. The reply only confirms/rejects the target stored by the backend; neither client hint nor model output can reconstruct or change that target. Tests assert an exploding scope guard is never called on this fast path.

## 14. Negation

Candidate routing emits `negatedActions` separately from positive `writeIntent`. The verifier rejects write/negation conflicts and invalid domain/action pairs. Deterministically detected negation overrides contradictory model JSON. DEVELOPMENT result: 50/50 negation fields correct and zero false-positive S1 write intents.

## 15. Ambiguity

The contract distinguishes `NONE`, `LEXICAL`, `REFERENCE`, `MULTI_INTENT`, `MISSING_ARGUMENT` and `PENDING_ACTION`. Ambiguous inputs retain bounded intent candidates and clarification suggestions; they do not authorize actions. DEVELOPMENT result: 46/50 ambiguity labels correct, so this field is not production-qualified.

## 16. Multi-Intent

Primary and secondary intents are separate, deduplicated allowlisted fields. Candidate scores are retained for observation. Three multi-intent DEVELOPMENT cases had 3/3 primary and 3/3 secondary correctness in the S1 no-model cascade; the single long case still missed one expected secondary intent.

## 17. Reference Resolution

Only a minimal structured recent-response kind can be supplied to the on-device parser. Chat text/history, health profile and backend tool results are not supplied. Short references can be marked unresolved/ambiguous, but the parser cannot manufacture a canonical ID or pending target. Four reference DEVELOPMENT cases were classified correctly by the no-model cascade.

## 18. Deterministic Verifier

The verifier checks intent/action allowlists, action-domain compatibility, negation conflicts, ambiguity consistency, confirmation validity and candidate compatibility. Invalid/unknown/malicious JSON falls back to deterministic candidates and records a reason code. Backend repeats strict allowlisting and strips any attempted raw text, entity, authority or policy field.

## 19. Shadow Integration

`SEMANTIC_ROUTER_MODE` accepts `off`, `shadow` and `enforced`, defaulting to `shadow`. In S1, `enforced` still remains observation-only and is explicitly not enforcement-ready. `AIChatProvider` sends the original chat frame first, then runs S1 asynchronously and sends a separate `semantic_shadow` frame. The backend handles that frame outside FIFO, records aggregate metrics and never passes it to `AgentOrchestrator`, prompts, tools or context.

## 20. Privacy

Raw/normalized messages, entities and slots stay on device. Backend telemetry contains allowlisted versions, enums, candidate scores, transform kinds, latency, model metadata/hash, verifier state and reason code only. It contains no user ID, prompt, profile, raw chat, normalized text, API key, tokens or reasoning.

## 21. Debug/Public Trace

S1 reuses the authenticated developer trace channel and emits sanitized metadata only. It adds no public/user-facing reasoning and no hidden chain-of-thought capture. Local debug output contains reason, whether SLM ran and raw message length—not the message itself.

## 22. Development Dataset

`semantic_router_s1_development.jsonl` contains 50 explicitly labelled `SYNTHETIC_DEVELOPMENT` cases: clean 5, no-diacritics 4, teencode 4, typo 3, slang 2, regional 2, mixed-language 3, negation 6, reference 4, multi-intent 3, ambiguity 3, write 3, pending action 4, safety 3 and long 1. It was used during implementation and is not a holdout or real-user metric.

## 23. Deterministic Router Baseline

The legacy baseline was captured before S1 tuning: primary 24/50 (48%), secondary 48/50, write 48/50 and authoritative scope 49/50, with two false-positive writes. Primary accuracy was 0% for teencode, slang, regional, reference, ambiguity and safety; 33.33% for typo/negation; 75% no-diacritics; 80% clean. After adding the deterministic fainting cue, authoritative scope became 50/50 while the legacy intent/write figures remained unchanged.

## 24. SLM Evaluation

Qwen native execution was attempted on LDPlayer. Device logs prove `libllama_jni.so` loaded through Houdini, the Q8 model loaded successfully, a 170-token prompt was tokenized and native decode began. No token/valid JSON completed within the 12-second inference budget. The first benchmark exposed a plugin lifecycle defect: stop was followed by controller reuse/free, producing decode failures and `SIGSEGV`. S1 now poisons the controller after timeout, waits for settlement and refuses unsafe free/reuse; this source fix passed analyze/unit tests but its device rerun did not reach a result marker before runner timeout. Therefore actual invocation is proven, successful SLM completion/parser quality is not.

## 25. Robustness Results

The S1 cascade with the model deliberately unavailable reached primary 47/50 (94%), secondary 49/50, write 50/50, negation 50/50, ambiguity 46/50 and confirmation 50/50. It had zero false-positive writes, zero pending-target mutation and zero invalid structured output after verification. This measures the implemented deterministic cascade on a development set tuned in the same task; it is not SLM quality or production readiness.

## 26. Mobile Performance

LDPlayer is connected as `emulator-5554` (Android 9/API 28, x86_64/Houdini, about 6 GB RAM). The first Q8 benchmark reported cold wall 33,372 ms, peak process RSS 621,060,096 bytes and `INFERENCE_TIMEOUT`; its reported 17–61 ms warm values were deterministic/failure fallbacks and are not SLM latency. No output token completed, so tokens/sec, warm inference p50/p95, parser-valid rate, Q4 comparison and thermal/battery metrics remain `NOT_MEASURED`. These results reject Q8-over-Houdini for an interactive router.

## 27. Failure / Fallback Behavior

Covered fallbacks: mode off, pending action, unsupported platform, missing model configuration/file, SHA mismatch, initialization failure, timeout, malformed JSON, unknown enum/action, verifier rejection and disposal. Every failure returns a typed reason and candidate result; it cannot authorize a write. The Android controller is cached, restricted to two threads, one generation at a time, 1024 context and bounded output; disposal releases native state.

## 28. Flutter Tests

- Pinned `flutter pub get`: passed.
- Pinned `flutter analyze`: passed, no issues.
- Pinned full `flutter test`: 195/195 passed.
- Focused S1 tests: 15/15 passed.
- Pinned `flutter build web --release`: passed; Wasm dry-run passed.
- Android debug build: passed; APK size 170,826,564 bytes with ARM64/ARMv7/x86_64 entries.
- `adb install -r`: passed. The normal app is foreground on LDPlayer as `com.example.app/com.example.health_app.MainActivity` with no fatal error after final launch.
- Firebase Google Sign-In is not qualified: without the project-specific `google-services.json`/registered signing SHA it returns `ApiException: 10`. The build uses explicit checked-in Firebase options and the app itself still launches.

## 29. Backend Tests

- Container: Python 3.11.16, pytest 8.4.2.
- Focused semantic/pending/scope/context suite: 96/96 passed.
- Full suite with two uncollectable root-layout modules explicitly excluded: 1112 passed, 9 skipped, 6 failed.
- All six failures are environment-layout failures: two exercise tests cannot read `/app/apps/mobile/...`, one Plan qualification loader assumes a parent above `/app`, and three research tests assume four parents above `/app`.
- An unfiltered collection also fails in two modules for the same `/app` parent-index assumption. Consequently the backend baseline is not green even though no S1 test failed.

## 30. Frozen Artifact Verification

S1 did not edit research source/manifests, D3 artifacts, Plan engine/tool/pending source files, canonical nutrition data/manifests or canonical exercise data/manifests. Research corpus verification passed with 636 chunks/embeddings and `SCIENTIFIC_IDENTITY_MATCH`. Frozen-focused tests had 60 passes and three `/app` parent-path failures. Five P2.1R implementation hashes were already mismatched before S1 (`pending_user_action.py`, `plan_v2.py`, `contracts.py`, `engine.py`, `persistence.py`); S1 neither created nor repaired that historical drift. Therefore `FROZEN_ARTIFACTS_UNCHANGED` means zero S1 delta, not that the pre-existing worktree satisfies every freeze manifest.

## 31. Known Limitations

- Native on-device invocation occurred, but no valid SLM completion; there is still no human-labelled Vietnamese holdout.
- The DEVELOPMENT set was used while refining rules; its 94% result is optimistic engineering evidence.
- No first-party Q4 source, signed delivery manifest or device storage/update policy. Q8 was manually checksum-pinned for DEVELOPMENT only.
- The selected Flutter plugin has an unverified publisher, API 26 minimum and ARM64 native focus; LDPlayer x86_64 would rely on Houdini compatibility.
- No iOS runtime. Android normal-app build/install is qualified only on this LDPlayer instance; model-enabled execution is rejected on it.
- Ambiguity remains 46/50 and long-message secondary intent 0/1 on DEVELOPMENT.
- Backend full-suite/frozen baseline is obscured by container repo-root mount defects, and P2.1R has pre-existing hash drift.
- S1 changes Android minimum API from the Flutter default 24 to 26. The repository's duplicate Groovy/Kotlin Gradle files should be consolidated later.
- Google Sign-In needs the authentic Firebase Android config plus registered package/signing SHA; no fake config was generated.

## 32. Recommended Next Step

Run the same checksum-pinned model on a real ARM64 phone, or replace the current plugin with a runtime that ships/test x86_64 and has cancellation-safe native lifecycle. Select a first-party/approved Q4 artifact before further latency work. Provision the real Firebase Android config separately. Build a human-labelled Vietnamese holdout and keep S1 fail-open/off on production routing until parser-valid, hard-gate, quality, lifecycle and performance thresholds pass manual review.

```text
SEMANTIC_ROUTER_IMPLEMENTED = YES
ON_DEVICE_SLM_INTEGRATED = YES
ON_DEVICE_SLM_ACTUALLY_EXECUTED = YES
ON_DEVICE_SLM_COMPLETED_VALID_PARSE = NO
SEMANTIC_ROUTER_SHADOW_READY = NO
SEMANTIC_ROUTER_ENFORCEMENT_READY = NO
FALSE_POSITIVE_WRITE_INTENT = 0
PENDING_ACTION_TARGET_MUTATION = 0
SAFETY_CRITICAL_ROUTING_MISS = 0
PRODUCTION_BEHAVIOR_CHANGE_IN_SHADOW = 0
FLUTTER_BASELINE_GREEN = YES
BACKEND_BASELINE_GREEN = NO
FROZEN_ARTIFACTS_UNCHANGED = YES
```

`ON_DEVICE_SLM_ACTUALLY_EXECUTED = YES` means native model load/tokenization/decode were observed; it does not mean a completion succeeded. `SEMANTIC_ROUTER_SHADOW_READY = NO` is conservative because the model-enabled lifecycle fix lacks a successful device rerun and Q8/Houdini violates latency. The normal fail-open app remains usable with the SLM disabled. The zero safety miss is scoped to the three DEVELOPMENT safety cases after the deterministic hard-gate fix.
