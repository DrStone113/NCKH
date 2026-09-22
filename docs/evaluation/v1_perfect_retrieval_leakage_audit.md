# V1 perfect-retrieval leakage audit

Audited artifact: `evaluation/results/v1-frozen-provider-retrieval-20260921-r3/`.

## Finding

The corrected V1 retrieval result is reproducible but **not an independent estimate of retrieval quality**. Its purpose is to validate the frozen V1 corpus/provider wiring after the historical production-store error.

| Check | Result |
|---|---:|
| Evidence-present cases | 60 |
| Gold at rank 1 | 60 / 60 |
| Query contains exact normalized gold title | 45 / 60 |
| Query contains gold chunk ID | 0 / 60 |
| Query contains gold source/document ID | 0 / 60 |
| Unique normalized queries | 80 / 80 |
| Gold construction | deterministic UUID5 from selected frozen source record |
| Gold taken from a retrieval run | No |

`scripts/build_evaluation_v1.py` selects source records and derives the expected chunk identifier from the same stable UUID5 convention used by the frozen corpus. This is better than taking a retriever output as gold, but it creates an easy, title-heavy closed-world retrieval task. The 1.0000 Hit@1/3/5 and MRR therefore establish correct provider/corpus materialization and deterministic retrieval compatibility—not external validity, clinical correctness, or final acceptance performance.

V1 files and historical outputs remain immutable. The final acceptance benchmark must use a separately authored, contamination-controlled evaluation set whose gold is assigned from source records independently of final retrieval output.
