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
