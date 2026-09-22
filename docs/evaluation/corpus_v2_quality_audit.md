# Corpus V2 quality audit

Corpus: `offline-v2-3891`  
Technical freeze hash: `5c6abe875f1f1c5ea5bbafe2334db1f21849e123b688ac8100bcf6af0f4ad200`

## Result: NOT QUALIFICATION-READY

The materialization verifier passed: 3,891 chunks, 3,891 embeddings, zero dynamic rows, matching corpus hash, and 20 sampled embedding norms of 1.0. It uses BAAI/bge-m3 revision `5617a9f61b028005a4858fdac845db406aefb181`, 1024 dimensions, and L2 normalization.

However, the post-build quality audit found **65 exact duplicate `content` strings** across otherwise distinct source records. Content hashes include source identity and therefore did not collide, but that is not a substitute for a duplicate-content audit. The corpus had already been technically frozen when this audit was run; it is not modified or silently re-frozen.

| Check | Result |
|---|---|
| Empty content | 0 |
| Broken Unicode / HTML residue in normalized projection | no failures observed by normalizer |
| Content length (min / median / p95 / max) | 76 / 519 / 593 / 1,785 characters |
| Missing included-source provenance | 0 |
| Missing included-source license metadata | 0 |
| Exact duplicate content | **65 — FAIL** |
| Dynamic rows | 0 |

## Distribution

| Source | Records |
|---|---:|
| USDA FoodData Central SR Legacy (CC0) | 3,000 |
| Existing Wger snapshot (record-level CC0 / CC-BY-SA) | 885 |
| HHS physical-activity source-linked summaries | 6 |

| Domain / language | Count |
|---|---:|
| Food / English | 3,000 |
| Exercise / English | 885 |
| Guideline / Vietnamese | 6 |

No Vietnamese food-composition projection was included because its existing source registry requires redistribution review. No NIH ODS bulk text was included because fact-sheet-specific acquisition was not completed.

## Required next step

Create a new corpus version from a deterministic deduplicated source projection, audit it **before** embedding, and freeze that new version. Do not alter `offline-v2-3891` or use it for final V2 qualification.
