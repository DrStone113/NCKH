# NCKH acceptance qualification summary

The corpus was verified as `offline-acceptance-vn-4954` with hash `f48b35561f421be720c53a607740ac51a5e8e74b598b081e85588a5eef10777a`. No corpus, frozen test artifact, retrieval threshold, embedding, RRF, query normalization, routing policy, or oracle label was changed.

The harness freezes a 200-case architecture projection and answer rubric before calls, and supplies the frozen research corpus through opt-in dependency injection only. It has no production table write and leaves the ordinary runtime default unchanged. Result artifacts are in `evaluation/results/acceptance-full-pipeline-001/`.

Qualification cannot proceed to research-report or acceptance-demo readiness: generation awaits credential rotation attestation; all 12 real E2E scenarios await Firebase test credentials; safety has one critical miss and an unmeasured persisted Plan-save gate; routing has three critical health misses and one false-positive write intent. No new benchmark was generated, and no commit or push was made.
