# Acceptance architecture mapping

The frozen Vietnam-first acceptance set is `evaluation/acceptance_vn/cases.jsonl` (200 cases). Its read-only architecture projection is `evaluation/acceptance_vn/expected_channels.json`, SHA-256 `d28e3e308b3b5c98c489a5e00a536ba63ff447bbb01db6188fde6844dd00638e`; source-case SHA-256 is `f5a539aa055196650b1c948fd797d6839db1620f1e5a4c7625b059d6f591512b`.

| Expected channel | Cases | Contract |
| --- | ---: | --- |
| FOOD_TOOL | 75 | `search_food_nutrition`; RAG forbidden |
| DISH_TOOL | 20 | `search_dish_catalog`; RAG forbidden |
| EXERCISE_TOOL | 25 | `search_exercise_catalog`; RAG forbidden |
| RAG_KNOWLEDGE | 55 | `query_rag`; grounded corpus evidence required |
| NO_EVIDENCE | 25 | bounded evidence limitation; RAG forbidden |

The projection is derived from the existing context-planner matrix and scope guard, not from model output or expected answer text. It was frozen before any generation call. The qualification adapter reads only `research_knowledge_chunks` and `research_chunk_embeddings` for `offline-acceptance-vn-4954` / `f48b35561f421be720c53a607740ac51a5e8e74b598b081e85588a5eef10777a`; normal runtime defaults and production RAG tables are unchanged.
