# N3.3 ADAPTIVE RANKING REMEDIATION REPORT

Work in progress. PRODUCT ENGINEERING; SHADOW ONLY.

## Historical N3.3 Findings

Historical report, replay, test scenarios and 377 protected files were hashed
before remediation in `validation/n3_3r/historical-freeze-v1.json`.
No initial hash drift was present. Historical results remain request precedence
regressed, diversity collapse, and one invalid canonical reference accepted.

## Pipeline Root Causes

`RecommendationRankerV2._hard_pass` checks mapping status and nutrition presence
through RecipeQualityGate, but does not resolve canonical IDs or source records.
`_explicit_same_dish` only clears a repeat penalty; preference can still win
the final weighted sort. `_repeat_penalty` caps exact-dish pressure at .70,
weighted by .07; this cannot guarantee rotation against saturated preference.

The dedicated route loads candidates and owner history/profile, ranks, logs a
shadow alternative, then constructs/persists RecommendationMemoryEntry. Chat
projects the already selected canonical tool result and constructs an exposure.
Neither event-construction boundary re-resolves the selected source identity.

Implementation dependencies justified within the protected-file exception:

- `adaptive/intelligence.py`: shared pre-score eligibility and categorical
  request/repetition precedence; existing numeric weights remain unchanged.
- `adaptive/delivery.py`: shared selected-candidate validation before exposure.
- `adaptive_router.py`: typed current request, authenticated owner binding,
  source registry injection, and validation before constructing the event.
- `services/agent/orchestrator.py`: same defense before chat exposure creation.
- `adaptive/repository.py`: owner-scoped source lookup for the shared gate and
  defense before recording an exposure in the in-process repository.

No SQL schema/store changes, historical evidence edits, research changes,
production enablement, browser automation, commits or pushes are authorized.
