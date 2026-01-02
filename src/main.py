from __future__ import annotations

from fastapi import FastAPI

from src.adapters.api.controllers.realtime import router as realtime_router
from src.adapters.api.controllers.routes import router as routes_router

app = FastAPI(title="UrbanPath")
app.include_router(routes_router)
app.include_router(realtime_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
