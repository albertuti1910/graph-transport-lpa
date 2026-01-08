from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.adapters.api.controllers.realtime import router as realtime_router
from src.adapters.api.controllers.routes import router as routes_router

app = FastAPI(title="UrbanPath")
app.include_router(routes_router)
app.include_router(realtime_router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Ensure API errors are JSON so the frontend can display them.

    Starlette's default 500 handler may return plain text/HTML, which the
    demo frontend parses as JSON and displays as `{}`.
    """

    logging.getLogger("uvicorn.error").exception(
        "Unhandled exception", extra={"path": str(request.url.path)}
    )

    reveal = (os.getenv("URBANPATH_REVEAL_ERRORS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if reveal or isinstance(exc, (FileNotFoundError, RuntimeError, ValueError)):
        detail = str(exc) or exc.__class__.__name__
    else:
        detail = "Internal Server Error"

    return JSONResponse(status_code=500, content={"detail": detail})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
