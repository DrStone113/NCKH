# RAG V1–V2 comparison

| Property | V1 | V2 technical freeze |
|---|---:|---:|
| Corpus version | `offline-v1-636` | `offline-v2-3891` |
| Records | 636 | 3,891 |
| Frozen retrieval result | Hit@1/3/5 = 1.00 on automated trace-derived oracle | Not measured |
| Food | 525 foods plus 90 dishes and small nutrition set | 3,000 USDA CC0 food profiles |
| Exercise | 10 records | 885 Wger records with license metadata |
| Guideline | none | 6 source-linked summaries |
| Qualification status | Retrieval wiring/corpus path verified; broader V1 incomplete | Not qualified: duplicate-content and contamination-review blockers |

The record-count increase is a coverage change, not evidence that V2 is superior. There is no valid shared independent holdout and no statistical superiority claim.
