# Real-auth E2E execution matrix (existing `scenarios_v1.yaml`)

This classifies the twelve frozen scenario definitions; it does not add or change cases. `writes_data` includes chat/session persistence or Plan preview records, even where the asserted business outcome is "no observation write". All created state requires exact-owner cleanup.

| scenario_id | category | requires_profile | requires_chat_model | requires_user_b | writes_data | cleanup_needed |
|---|---|---|---|---|---|---|
| E2E-01 | CHATBOT_DEPENDENT | YES | YES | NO | YES | YES |
| E2E-02 | CHATBOT_DEPENDENT | YES | YES | NO | YES | YES |
| E2E-03 | CHATBOT_DEPENDENT | YES | YES | NO | YES | YES |
| E2E-04 | AUTH_AND_DATA_ONLY | YES | NO | NO | YES | YES |
| E2E-05 | AUTH_AND_DATA_ONLY | YES | NO | NO | YES | YES |
| E2E-06 | AUTH_AND_DATA_ONLY | YES | NO | NO | YES | YES |
| E2E-07 | AUTH_AND_DATA_ONLY | YES | NO | NO | YES | YES |
| E2E-08 | CHATBOT_DEPENDENT | YES | NO | NO | YES | YES |
| E2E-09 | CHATBOT_DEPENDENT | YES | YES | NO | YES | YES |
| E2E-10 | CHATBOT_DEPENDENT | YES | YES | NO | YES | YES |
| E2E-11 | CROSS_OWNER_SECURITY | YES | NO | YES | YES | YES |
| E2E-12 | CHATBOT_DEPENDENT | YES | YES | NO | YES | YES |

E2E-04–07 can use the normal authenticated Plan V2 HTTP/UI surface without model generation. E2E-08 still uses the authenticated chat transport, but its urgent-health reply is guarded deterministically before the answer model. E2E-11 requires an A-owned Plan created through the product API and checks both bearer principals. A REST-only subcheck is not a full browser E2E pass where the YAML also requires browser trace/screenshots.

## Execution checkpoint (2026-09-23)

Both dedicated principals authenticated with real Firebase earlier in this run; both profiles were persisted through the Flutter onboarding flow and verified before Plan API subchecks. The Plan API created, saved, re-read, and checked idempotency for both owners; the security and lifecycle subchecks were also exercised, but the required browser traces, screenshots, edit revision, and exact-owner cleanup remain incomplete. An authenticated chatbot WebSocket smoke previously returned a nonempty response. These subchecks do **not** qualify a complete YAML scenario.

The current worker environment has no `E2E_TEST_EMAIL_A`, `E2E_TEST_EMAIL_B`, or `E2E_TEST_PASSWORD`; browser re-login and cleanup cannot be rerun until they are provided securely to the executing process. No auth bypass or fabricated model answer was used. The currently serving backend reports `sp/qwen3.8-fast`; a minimal `/chat/completions` probe returned HTTP 200 and nonempty content. This is an operational E2E route, not a frozen final-evaluation configuration.

| SCENARIO_ID | CATEGORY | AUTH | PROFILE_PRECONDITION | EXECUTION | STATE_ASSERTION | CLEANUP |
|---|---|---|---|---|---|---|
| E2E-01 | CHATBOT_DEPENDENT | PASS | PASS | BLOCKED | NOT_REACHED | NA |
| E2E-02 | CHATBOT_DEPENDENT | PASS | PASS | BLOCKED | NOT_REACHED | NA |
| E2E-03 | CHATBOT_DEPENDENT | PASS | PASS | BLOCKED | NOT_REACHED | NA |
| E2E-04 | AUTH_AND_DATA_ONLY | PASS | PASS | BLOCKED | NOT_REACHED | FAIL |
| E2E-05 | AUTH_AND_DATA_ONLY | PASS | PASS | BLOCKED | NOT_REACHED | FAIL |
| E2E-06 | AUTH_AND_DATA_ONLY | PASS | PASS | BLOCKED | NOT_REACHED | NA |
| E2E-07 | AUTH_AND_DATA_ONLY | PASS | PASS | BLOCKED | NOT_REACHED | FAIL |
| E2E-08 | CHATBOT_DEPENDENT | PASS | PASS | BLOCKED | NOT_REACHED | NA |
| E2E-09 | CHATBOT_DEPENDENT | PASS | PASS | BLOCKED | NOT_REACHED | NA |
| E2E-10 | CHATBOT_DEPENDENT | PASS | PASS | BLOCKED | NOT_REACHED | NA |
| E2E-11 | CROSS_OWNER_SECURITY | PASS | PASS | BLOCKED | NOT_REACHED | FAIL |
| E2E-12 | CHATBOT_DEPENDENT | PASS | PASS | BLOCKED | NOT_REACHED | NA |

`CLEANUP=FAIL` denotes known Plan test data for which a successful cleanup was not verified; `NA` denotes scenarios without a completed scenario run. `STATE_ASSERTION=NOT_REACHED` refers to the full browser-plus-state assertion, not the successful partial API checks.

E2E_DEFINED=12; E2E_EXECUTED=0; E2E_PASS=0; E2E_FAIL=0; E2E_BLOCKED=12. NON_CHAT_E2E_EXECUTED=0; NON_CHAT_E2E_PASS=0. CHATBOT_E2E_EXECUTED=0; CHATBOT_E2E_PASS=0. BLOCKED_SCENARIOS=E2E-01,E2E-02,E2E-03,E2E-04,E2E-05,E2E-06,E2E-07,E2E-08,E2E-09,E2E-10,E2E-11,E2E-12. Blocker for this checkpoint: credentials unavailable in the current worker process, not an unavailable generation route.

## Authenticated continuation (2026-09-23)

This section supersedes the earlier credential-blocked checkpoint **for the continuation only**; it is not a completed 12-case certification. The credentials supplied for this run were used only in process environment, not stored in this file. Both Firebase accounts authenticated again; both onboarding profiles remained readable. The UID-allowlisted reset ran after an inventory dry-run and again at the end without deleting profiles. Final inventory: zero owned SQL test rows and zero listed Firestore test documents for both users. The earlier `BLOCKED` rows above are historical, not current results.

FINAL_E2E_GIT_SHA=`ca2ddc7ea1fb2d4685ab18b9e02cbafe70611a3d`; E2E_GENERATION_MODEL=`sp/qwen3.8-fast`; E2E_RUN_TIMESTAMP=`2026-09-23T18:21:01+07:00`. The backend was restarted on that code state. Real-auth chatbot smoke returned a nonempty `done` event. The authenticated Plan V2 API generated and saved A/B revisions, verified exact hashes/readback and idempotency, checked lifecycle and denied cross-owner read/write in both directions with owner readback. A/B Flutter libraries displayed their respective exact revision cards without the other's card. Browser chat showed the corrected unsafe-weight reply and urgent-health escalation; neither created a meal observation. **These are partial workflows**, not completion of the YAML steps.

| SCENARIO_ID | CATEGORY | AUTH | PROFILE_PRECONDITION | EXECUTION | STATE_ASSERTION | CLEANUP | Reason full YAML did not pass |
|---|---|---|---|---|---|---|---|
| E2E-01 | CHATBOT_DEPENDENT | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | Dinner suggestion sent and no meal row appeared, but browser reload/trace and response-profile grounding not captured. |
| E2E-02 | CHATBOT_DEPENDENT | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | Catalog request sent; second negation was attempted while the first turn was still streaming, so no confirmed negated turn/trace. |
| E2E-03 | CHATBOT_DEPENDENT | PASS | PASS | NOT_EXECUTED | NOT_REACHED | NA | No pending catalog action, explicit confirmation, diary readback, or retry executed. |
| E2E-04 | AUTH_AND_DATA_ONLY | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | Exact Plan API preview/save/readback and library card verified, but UI preview-to-confirm sequence and required browser trace not captured. |
| E2E-05 | AUTH_AND_DATA_ONLY | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | API idempotency verified; specified WebSocket disconnect/reconnect and second-tab confirmation not performed. |
| E2E-06 | AUTH_AND_DATA_ONLY | PASS | PASS | NOT_EXECUTED | NOT_REACHED | NA | Existing Plan detail has no wired edit control; no typed meal replacement or immutable revision comparison executed. |
| E2E-07 | AUTH_AND_DATA_ONLY | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | API activate/pause/readback and UI detail verified separately; browser reload between transitions and active-domain readback not captured. |
| E2E-08 | CHATBOT_DEPENDENT | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | Urgent response observed in browser, no observation row, but reload/profile and Plan no-write readbacks plus required trace/screenshots incomplete. |
| E2E-09 | CHATBOT_DEPENDENT | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | Corrected reply rejected 10 kg/7 days and offered safer 0.5–1 kg/week; Plan Library comparison and full browser trace incomplete. |
| E2E-10 | CHATBOT_DEPENDENT | PASS | PASS | NOT_EXECUTED | NOT_REACHED | NA | Weight/activity were not updated in the UI, so the recommendation assertion cannot be made. |
| E2E-11 | CROSS_OWNER_SECURITY | PASS | PASS | INCOMPLETE | NOT_REACHED | PASS | Both-direction API denial, unchanged owner hash, and segregated Library cards verified; sign-out/sign-in browser trace and screenshots incomplete. |
| E2E-12 | CHATBOT_DEPENDENT | PASS | PASS | NOT_EXECUTED | NOT_REACHED | NA | Corpus-absent dosing question and retrieval trace were not executed. |

E2E_DEFINED=12; E2E_EXECUTED=0 (fully executed); E2E_PASS=0; E2E_FAIL=0; E2E_BLOCKED=0; E2E_INCOMPLETE=8 (partial workflow attempted); E2E_NOT_EXECUTED=4 (E2E-03, E2E-06, E2E-10, E2E-12). `STATE_ASSERTION=NOT_REACHED` means **the entire defined assertion set** was not reached, even when a partial invariant passed. `CLEANUP=PASS` refers to the verified final exact-owner reset, not to scenario-by-scenario intermediate resets. No external provider block remains; these are incomplete executions, not a model failure. Do not combine partial API checks into a full E2E pass.

Product fixes pushed during continuation: `da3de6a` (bound chat restore / new-session input), `651276a` (Rules emulator port isolation), `ca2ddc7` (accent-folded `nghiêm ngặt` falsely matched emergency `ngat`). Final regression: backend 129 passed/0 failed/2 skipped; Flutter focused tests 17 passed/0 failed; Flutter analyze passed; Flutter Web build passed; Firestore Rules 10 passed/0 failed using isolated port 8181 and JDK 21. No report or answer-quality evaluation was changed.

## Execution campaign checkpoint (2026-09-23 23:15 +07:00)

The current product HEAD is `3d945ae16d6f61588ebed1a54cb0941cbcb9a25d`, **not** a `FINAL_E2E_PRODUCT_SHA`: no single-snapshot run has completed all 12 YAML workflows. Neither the product fixes below nor the earlier API/browser subchecks may be combined into a final PASS count. The earlier table's corrected `INCOMPLETE`/`NOT_EXECUTED` results remain the latest per-scenario outcomes; its E2E-06 description that no edit control exists is now historical. Typed Plan meal replacement was added at `3d945ae` but has not been validated end-to-end on the live Plan API.

On the current product code, both dedicated users again authenticated through real Firebase Email/Password and their profiles were available. The backend reported `sp/qwen3.8-fast`; a real authenticated chatbot smoke emitted a nonempty `done`, and owner-scoped history contained both the user and assistant messages. The owner-allowlisted reset then removed that smoke session. Subsequent attempts to run E2E-01 through the new Flutter Canvas browser runner alternated between an unsubmitted login dialog and a chat session with no saved turn; the latest timeout was cleaned up. Screenshot and sanitized stage traces are stored only outside the repository under the pre-approved temporary directory. These runner failures do not establish a failed product assertion or a completed scenario. Final dry-run inventories for both users: profile exists; no listed owner Firestore test documents or owner SQL test rows.

New separately pushed product fixes: `e1b364d` prevents a failed chat message INSERT from being acknowledged as saved (backend chat/orchestrator-focused tests: 106 passed); `3d945ae` adds a typed meal replacement preview and explicit save UI, with production-like lifecycle targets in the widget regression (2 passed; Flutter analyze clean). The edit workflow has **not** been shown to pass E2E-06. A clean 12-case execution, per-case complete readback, scenario-level screenshots, and a final broad regression run are still required; `E2E_EVIDENCE_COMMIT` for a completed run does not exist.

CURRENT_CHECKPOINT: E2E_DEFINED=12; E2E_EXECUTED=0 (fully executed); E2E_PASS=0; E2E_FAIL=0; E2E_BLOCKED=0; E2E_INCOMPLETE=8; E2E_NOT_EXECUTED=4. INCOMPLETE=E2E-01,E2E-02,E2E-04,E2E-05,E2E-07,E2E-08,E2E-09,E2E-11; NOT_EXECUTED=E2E-03,E2E-06,E2E-10,E2E-12. Qwen is available; the unfinished browser runner and missing full workflows are not an external-provider BLOCKED result.

## Regression and runner update (2026-09-23)

The full backend suite on the product lineage plus test-only commit `89b3938` yielded 1409 passed/0 failed/10 skipped. A Hypothesis property previously reported `FlakyFailure` solely for exceeding its 200 ms deadline (501 ms on one run, 196 ms on retry); `89b3938` removes that timing oracle from the idempotence property without changing its equality assertion. The full Flutter suite yielded 225 passed/0 failed; `flutter analyze --no-pub` passed; the isolated Firestore Rules run yielded 10 passed/0 failed. These regressions verify code quality, **not** scenario qualification. Real Firebase profiles and exact-owner dry-run inventories were checked again after the final browser attempt: A/B profiles exist and their listed test records are empty.

Browser attempts still did not produce a complete E2E-01 workflow: the new Canvas runner intermittently failed to submit the visible login dialog, opened a still-loading chat-history sheet, or timed out after creating a session with no completed turn. Each surviving exact-owner session was removed with the allowlisted reset. The older direct authenticated WebSocket smoke does not substitute for the required UI reload and grounding assertions. New exploratory runner files remain untracked and are not a final E2E harness; no synthetic PASS, fabricated output, token, or credential was committed. The per-case outcome counts above remain unchanged. No `FINAL_E2E_PRODUCT_SHA` or completed-run evidence commit exists.
