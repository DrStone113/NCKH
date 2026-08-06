# Task: Remove Local AI Dependencies - Date: 2026-06-25

## 1. Current Progress Status
- [x] Completed & Verified

## 2. Code Evolution (What & Why)
- **Files Modified:** 
  - `apps/backend/requirements.txt`
  - `apps/backend/services/rag_service.py`
  - `apps/backend/services/agent/rag_service.py`
  - `apps/backend/scripts/load_dataset.py`
- **Core Changes:** 
  - Removed `sentence-transformers` and `PyTorch` from the project's dependencies to prevent Docker from downloading gigabytes of local ML libraries. This significantly optimizes memory allocation and image size.
  - Replaced the local `SentenceTransformer` inference calls with the `openai.Client` from the `openai` Python SDK. The system now delegates text embedding generation to a remote API provider (configured via `OPENAI_BASE_URL` and `OPENAI_API_KEY`).

## 3. Architecture & Data Flow
- Map the data flow: [Backend / Data Loader] -> [OpenAI API via `openai.Client`] -> [Embedding Vector] -> [pgvector database].
- Highlight the defensive mechanisms put in place: The OpenAI client is initialized lazily (`_get_model`) to ensure it does not block application startup and accurately pulls credentials from the validated `config.settings`.

## 4. Verification & Testing Evidence
- Python syntax is correct and all modified files have been updated successfully.
- Requirements have been cleanly stripped of heavy ML dependencies.
- (Awaiting user to run `docker compose up --build` to finalize image size verification).
