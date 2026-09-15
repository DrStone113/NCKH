"""Run the isolated authenticated Plan V2 API used by the P2.2 browser gate.

This is deliberately a thin host around the real router.  It is not a mock,
does not seed plans, and must be pointed at an acceptance-owned PostgreSQL
database through ``DATABASE_URL``.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from modules.plans.v2_router import router


def create_app() -> FastAPI:
    app = FastAPI(title="P2.2 Plan V2 acceptance API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:4173", "http://localhost:4173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)
    return app


if __name__ == "__main__":
    uvicorn.run(create_app(), host="127.0.0.1", port=8091, log_level="warning")
