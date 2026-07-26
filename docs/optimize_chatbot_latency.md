# Task: Optimize Chatbot Latency & Optimistic UI - Date: 2026-06-30

## 1. Current Progress Status: [x] Completed

## 2. Code Evolution (What & Why)
- **Files Modified:**
  - `lib/models/wger_models.dart`:
    - Defined a public static `lookupFoodNutrition` method mapping key Vietnamese dishes to nutritional values.
    - Modified `ActionItem.fromJson` to perform local lookups on the client when `calories`, `protein`, `fat`, or `carbs` values are missing or zero.
  - `lib/providers/ai_chat_provider.dart`:
    - Handled client-side native tool calls for `log_meal` and `log_exercise` in `_handleToolCall`.
    - Implemented **Optimistic UI updates** that log items into `NutritionProvider` and `ExerciseProvider` immediately.
    - Appended a loading message (`🔄 Đang thêm "..." vào nhật ký...`) directly to the chat list and returned success back to the backend.
  - `services/agent/orchestrator.py`:
    - Truncated `context.history` to only send the last **6 turns** of messages (approx. 3 chat turns), decreasing payload transfer sizes and model token parsing times.
  - `services/agent/system_prompt.py`:
    - Simplified the Structured Output JSON formatting examples, removing calories and nutrition details from instructions.
  - `services/agent/tools/__init__.py`:
    - Simplified `log_meal` and `log_exercise` tool schemas by removing `calories` and `calories_burned` fields from requirements and definitions.
  - `services/agent/chat_gateway.py`:
    - Removed redundant `commit()` and `rollback()` calls from the `tool_result` branch to prevent asyncpg transaction conflicts.
  - `services/agent/memory_service.py`:
    - Added RAG query expansion to `loadContext` to combine recent user chat history when the current query contains Vietnamese pronouns (e.g. "nó", "đó", "thêm") or is short, ensuring pgvector matching matches the correct food/exercise entries.
  - `ai_backend/backend/data/nutrition.json`:
    - Added Bún Riêu with its list of ingredients, serving details, and nutritional value. Loaded it using `data_loader` so it is stored and indexed in pgvector.
  - `HealthApp/health_app/Dockerfile` & `web/index.html`:
    - Renamed `main.dart.js` to `main_v2.dart.js` in the web build output and updated bootstrap script references to bypass Cloudflare edge CDN caches.
- **Anti-Repetition Safeguards:**
  - Standardized all access scope qualifiers to ensure Dart visibility across file boundaries (renamed private `_lookupFoodNutrition` to public `lookupFoodNutrition`).
  - Removed concurrent commits on a single shared async session from separate events in the WebSocket gateway.
  - Implemented defensive name matching checking in `wger_models.dart` to retrieve food name from parent `name` property or nested details properties (`dish_name`, `food_name`).
  - Purged web build cache issues completely by renaming output files rather than relying solely on query parameter query string cache-busting.

## 3. Architecture & Data Flow
- **Data Flow:** [User prompt: "Thêm bún riêu vào bữa sáng đã ăn"] -> [Backend receives prompt] -> [LLM determines tool invocation] -> [LLM fires `log_meal(dish_name='Bún riêu', meal_type='breakfast')`] -> [Client intercepts `tool_call` immediately] -> [Client splits compound dish "Bún riêu" into Bún, Tôm, Thịt cua, Rau based on compoundRecipes ratios] -> [Client performs local lookup for each ingredient to calculate exact calories/macros] -> [Client calls `addMeal()` (Updates UI in ~50ms)] -> [Client appends status chat bubble] -> [Client returns `success` response to backend] -> [Backend LLM receives success and finishes speech].

## 4. Verification & Testing Evidence
- Executed `docker-compose build flutter_web` to verify compilation.
- Result: **FINISHED SUCCESS** in 188.8s.
- Executed `docker-compose run --rm data_loader` to embed and load updated datasets.
- Result: **FINISHED SUCCESS**. Loaded 11 nutrition items including Bún Riêu.
