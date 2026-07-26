## [2026-07-25]
- **Added:** Implemented **3-Module Modular Architecture** (Module 1: Dinh dưỡng, Module 2: Thể chất, Module 3: Sức khỏe Tinh thần & Lifestyle).
- **Added:** Created `lifestyle_model.dart`, `lifestyle_provider.dart`, and `lifestyle_screen.dart` for Module 3 management in Flutter.
- **Added:** Registered client tools `get_lifestyle_logs`, `log_lifestyle`, `set_lifestyle_reminder` in FastAPI backend `tools/__init__.py` and mapped domain modules via `DOMAIN_MODULE_MAP`.
- **Added:** Updated `system_prompt.py` to instruct LLM on modular domain routing and lifestyle tool invocation strategies.
- **Added:** Created scientific research design document `docs/MODULAR_ARCHITECTURE_DESIGN.md` for NCKH paper publishing.
- **Fixed:** Fixed parameter structure mismatch in `wger_food_search_widget.dart` by properly nesting `MealItem` within `MealModel.items`.
- **Lessons Learned (Anti-Repetition):** Always construct domain models (e.g. `MealModel`) with their exact expected parameters (`items: [MealItem]`) rather than passing raw item properties directly to top-level model constructors.

## [2026-06-30]
- **Added:** Real-time token streaming to Flutter UI (word-by-word rendering).
- **Added:** Locked input TextField and disabled send button when AI chatbot is streaming responses.
- **Added:** Optimistic UI updates for `log_meal` and `log_exercise` client-side tool calls in Flutter.
- **Added:** Local keyword-based nutrition macro lookup inside client `ActionItem` models.
- **Added:** Bún Riêu to backend `nutrition.json` dataset and re-loaded into PostgreSQL vector database (RAG).
- **Added:** Compound recipe splitting in frontend `wger_models.dart` and `ai_chat_provider.dart` to automatically expand compound dishes (such as Bún riêu, Phở bò, Phở gà, Bún chả, Bánh mì kẹp, Cơm tấm) into constituent ingredients for accurate local macro calculations.
- **Optimized:** Truncated context history window to 6 turns in the orchestrator to decrease LLM response latency.
- **Optimized:** Stripped `calories` and `calories_burned` calculation requirements from LLM system prompts and tool schemas.
- **Fixed:** Chatbot message bubble displays stream content on token arrival instead of hiding it in the thinking indicator.
- **Fixed:** Public accessibility of `lookupFoodNutrition` static helper across Dart libraries.
- **Fixed:** Resolved `InterfaceError: another operation is in progress` database crash by removing redundant concurrent `commit()` calls from the WebSocket `tool_result` event handler.
- **Lessons Learned (Anti-Repetition):** Ensure that `notifyListeners()` is triggered on real-time stream token updates to notify widgets. Avoid library-private prefixes (`_`) for static model helpers that need to be accessed by providers across library boundaries. Do not run database commits (`commit()`) concurrently on a single shared async SQLAlchemy session when other asynchronous tasks are actively executing queries/updates.
## [2026-06-25]
- **Added:** System Prompt instructions for generating `StructuredResponse` JSON to enable Flutter action cards (Food/Exercise UI).
- **Added:** System Prompt rules enforcing strict Medical Decorum (no diagnosis).
- **Added:** Backend `orchestrator.py` now parses `{"type": "structured", ...}` JSON from LLM's text stream and routes it via WebSocket.
- **Fixed (AI Hallucination):** The AI fabricated an excuse ("hệ thống hồ sơ đang tạm thời không phản hồi") to ask the user for profile data manually when asked to create a plan. The system prompt was updated to aggressively enforce calling `get_user_profile` for ALL tasks and strictly forbade it from making excuses or asking the user for profile data.
- **Lessons Learned (Anti-Repetition):** Always check if the application is running via Docker or natively. When running via Docker, verify if the files being edited are mounted via volumes or baked into the image. If baked in, a full `docker-compose up --build` is required. Also, for LLMs with strong chat instincts (like DeepSeek), ensure stream parsing handles late-arriving tool calls.
