# PLAN TOOL V2 P2.1 — EVIDENCE-ONLY ACCEPTANCE & RELEASE QUALIFICATION

## Result

**NOT QUALIFIED FOR RELEASE.** No production or staging rollout was enabled, no
feature code was changed, no acceptance input was changed, and no commit or
push was made in this P2.1 run.

The run stopped before holdout scoring because two prerequisite hard gates
failed: the official Flutter baseline is unavailable locally, and the frozen
acceptance corpus is entirely leaked into the development-only natural prompt
set. Reporting a pass rate, comparator score, weekly/nutrition acceptance, or
release-readiness result from that corpus would not be evidence-based.

## Immutable Baseline

- Baseline commit: `32abb17d3e50455184c7d48bc80f01b8548513e5`
  (`feat: complete verified plan and workout foundations`).
- `origin/main` resolved to the same commit at inspection time.
- The worktree was clean before this report was added.
- No source, migration, test, policy, corpus, or acceptance case was edited in
  this run. The only intended worktree change is this evidence report.

Selected source SHA-256 values:

| Path | SHA-256 |
| --- | --- |
| `apps/backend/services/plan_engine/contracts.py` | `936ff8e65fb77bb775a33dfe888564b6d868033515b7725822cea013bd6356f2` |
| `apps/backend/services/plan_engine/engine.py` | `a9f5f5143e794cffdaab1006ee365eb4dc2ba57f64e9909180c0f6bae29e3e2d` |
| `apps/backend/services/plan_engine/comparator.py` | `77f52544cc6b07bca9882bb823d1687e85775c5066543db0b6602ae9d7ed711a` |
| `apps/backend/services/plan_engine/weekly_scheduler.py` | `e694183a71bbcd49b32988ab03673a8d53361c6337243168d773a6c8867864ff` |
| `apps/backend/services/plan_engine/nutrition_horizon.py` | `159e625d851d850080eaf62bd27d03f7745c9fbc48eff3c6eb2601f18e6a025c` |
| `apps/backend/services/plan_engine/persistence.py` | `06bd7c9255914cef6c04ca0f1b44372cb9fe85615329df9a620dae20f22eff11` |
| `apps/backend/services/agent/tools/plan_v2.py` | `ddd9d0912fe66bce682081aaeddbdf3e0c87a881e049b26302f2f254b9bfce6d` |
| `apps/backend/services/agent/pending_user_action.py` | `da08aaf5b50279cced863ccaa6757f421175c6af04bbfe042ed2b65887c29352` |
| `apps/mobile/lib/widgets/versioned_plan_card.dart` | `3bfea3396a577498a6e7823c76240741b299a2179249f5fd20a25c02102db606` |

Migration SHA-256 values:

| Migration | SHA-256 |
| --- | --- |
| `011_plan_tool_v2_p2_enforced.sql` | `1aba2faae1777ee3e5fa669a2dfce6863bca6b5d853bb01cb1d10697085fc977` |
| `012_plan_tool_v2_p2_item_order.sql` | `2aca3e59bff2426a91d31d65eebae5b1a28a25b3881a49cd8866461b404f23d8` |
| `013_plan_tool_v2_p2_logical_item_identity.sql` | `bf0df773e40a6f0b0b7540dfda0fd0be144d3f32f0ca2fc387ef0c8d455893ef` |

## Toolchain Baseline

Required official acceptance baseline: Flutter `3.44.8`, Dart `3.12.2`, and
CPython `3.10.21`.

- CPython: `3.10.21` — available and used for backend evidence.
- Pytest: `8.4.2`.
- Installed Flutter: `3.47.1`.
- Installed Dart: `3.13.1`.
- No `fvm` command or separate local Flutter 3.44.8 installation was found in
  the inspected tool locations. Flutter was not downloaded, installed, or
  switched during this evidence-only run.

`TOOLCHAIN_BASELINE_VERIFIED=NO`. Consequently, no Flutter 3.47.1 result is
used as a substitute for official acceptance, and no Flutter acceptance suite
was run in this P2.1 qualification.

## Frozen Acceptance Inputs and Independence Audit

The input files were read without modification:

| Input | SHA-256 | Observed content |
| --- | --- | --- |
| `acceptance-v1.json` | `6e5a24ef394eaefd6e254c2155e10dc002763fad21e32056f88c327890b0a712` | 120 declared cases |
| `acceptance-manifest-v1.json` | `d437a36a2f686c5218594ab15386e97114abad2e0830e200c253c1b0ecef732a` | declares 120 cases and frozen-before-first-run |
| `natural-development-v1.json` | `9e8a43f49aa06f3e469aad187c06242e49181a373e716c4966d9e39223b427f8` | 50 prompts marked `development_only` |

The manifest's declared area distribution totals 120: nutrition 30,
single-session workout 30, weekly workout 30, combined health 15, and
lifecycle/adversarial 15.

The P1 fixture actually enumerates **106** unique development scenarios, not
the 103 cited in the P2.1 request. This is an inventory discrepancy and must
be reconciled before an audit can assert the requested `P1 103` split.

### Leakage Results

Normalization (Unicode normalization, lower-casing, and punctuation/whitespace
removal) found:

- 120 acceptance records but only **50 unique prompts**.
- **70 duplicate records** beyond the first instance, arranged largely as
  three copies of the same prompt.
- Exactly **50/50 unique acceptance prompts** equal a prompt in
  `natural-development-v1.json`.
- Therefore **120/120 acceptance records** are exact matches for prompts
  explicitly classified `development_only` and
  `not_independent_acceptance=true`.

This is direct development-set leakage, not merely a possible paraphrase.
The corpus cannot be treated as a holdout and no score from it is valid for
release qualification.

## Oracle Governance

Each current case references `p2-engineering-oracle-v1` and contains generic
hard invariants such as `NO_PLANNED_TO_ACTUAL_LEAKAGE`,
`NO_UNINTENDED_WRITE`, and `CANONICAL_REFERENCES_ONLY`.

The frozen files do not identify a human oracle author/reviewer, review date,
case-specific expected semantics, ambiguous-case resolution, or a legacy
source. The V2 comparator was therefore not used to judge itself, and no
semantic score was calculated.

`INDEPENDENT_ORACLE_VERIFIED=NO`.

## Acceptance Execution

**NOT STARTED / UNSCORABLE.** The 120 cases were intentionally not passed to
the comparator, scheduler, nutrition horizon, chatbot, persistence, or any
staging route. This preserves the failed corpus as evidence and avoids an
invalid post-hoc score.

Accordingly, the following have no P2.1 acceptance result: comparator
better/equivalent/acceptable/regression/not-comparable classification; intent
match rate; reference-chain rate; hard-violation count; weekly acceptance;
multi-day nutrition acceptance; natural-language chatbot shadow E2E; actual
Plan-vs-Actual transport E2E; fresh PostgreSQL integration; auth matrix;
failure injection; concurrency; pending-action concurrency; performance; and
enforced staging/rollback checks.

All corresponding hard gates are **NOT PROVEN**, not passes.

## Blocked Component Status

The following `NO` values mean **`BLOCKED_NOT_EVALUATED`**, not
`FAILED_ACCEPTANCE`: no valid independent holdout existed when P2.1 stopped.

```text
PLAN_V2_COMPARATOR_READY = NO
reason = BLOCKED_NOT_EVALUATED

WEEKLY_WORKOUT_SCHEDULER_READY = NO
reason = BLOCKED_NOT_EVALUATED

NUTRITION_MULTIDAY_PLANNER_READY = NO
reason = BLOCKED_NOT_EVALUATED
```

## Static Lifecycle Observation (Not an Acceptance Score)

`PlanSqlRepository.set_status` permits `SAVED → ACTIVE` and `ACTIVE → PAUSED`,
but its allowed-transition map does not permit `PAUSED → ACTIVE`. The public
tool descriptor nevertheless advertises `resume`. This is a source-audit
finding requiring a future fresh-database lifecycle test after the frozen
input/toolchain prerequisites are repaired; it was not patched in this run.

## Non-acceptance Regression Evidence

These checks provide regression evidence only and do not override the failed
acceptance prerequisites:

- Backend on CPython 3.10.21: `840 passed, 2 skipped` in 90.75 s.
- `python -m compileall -q services`: passed.
- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: passed before this report was written.
- Frozen research corpus verifier: passed with scientific identity match.
  - corpus: `offline-v1-636`
  - frozen manifest: `5ed75adc4885b3b3b4f01554a4789605299dca965794819a76c81fc3e892afb1`
  - corpus hash: `b9bc6e3a1546740ef48f39a08688c2d1ce92f4e126dc0487d8603453b843d081`
  - scientific identity hash: `e549043d7f56431ab76cf6ce3015044d8f33aca1b743780212d97c12dcc0451a`

No fresh disposable PostgreSQL instance was started: its acceptance matrix is
downstream of a valid independent corpus and must not be represented as P2.1
acceptance while those input gates fail. No chatbot/staging service was
contacted.

## Required Next Evidence Run

This run must not be repaired retroactively. A subsequent qualification needs:

1. A newly authored, independently reviewed holdout corpus (120 unique cases),
   disjoint from every development/natural prompt, with a new manifest and
   recorded human oracle source, review, and ambiguity decisions.
2. Flutter 3.44.8/Dart 3.12.2 installed or otherwise reproducibly provisioned,
   followed by the official mobile suite.
3. A fresh PostgreSQL 16 run from schema through migrations 011–013, then the
   specified lifecycle, ownership, idempotency, transaction, concurrency, and
   failure-injection matrix.
4. Actual authenticated chatbot shadow and Plan-vs-Actual transport E2E
   evidence, followed only then by controlled enforced staging and rollback.

## Final Gate Matrix

| Gate | P2.1 status |
| --- | --- |
| `TOOLCHAIN_BASELINE_VERIFIED` | **NO** |
| `P2_1_HOLDOUT_INDEPENDENCE_VERIFIED` | **NO** |
| `INDEPENDENT_ORACLE_VERIFIED` | **NO** |
| `P2_1_COMPARATOR_ACCEPTANCE_READY` | **NO** |
| `P2_1_WEEKLY_ACCEPTANCE_READY` | **NO** |
| `P2_1_NUTRITION_MULTIDAY_ACCEPTANCE_READY` | **NO** |
| `P2_1_SQL_PERSISTENCE_ACCEPTANCE_READY` | **NO** (not rerun in qualified matrix) |
| `P2_1_AUTHORIZATION_ACCEPTANCE_READY` | **NO** (not rerun in qualified matrix) |
| `P2_1_CHATBOT_E2E_READY` | **NO** |
| `P2_1_ENFORCED_STAGING_READY` | **NO** |
| `P2_1_RELEASE_QUALIFIED` | **NO** |
