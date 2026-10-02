"""ABHEDYA-CHAKRA backend. Local-first FastAPI service."""
from __future__ import annotations

import os, time
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .api.compat import router as compat_router
from .config import API_VERSION, RAW_DIR
from .errors import ApiError, FastJSON, fail, new_request_id
from .core.store import STORE


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Load a CSV from data/raw at boot unless ABHEDYA_NO_AUTOLOAD is set."""
    import os, threading
    if not os.environ.get("ABHEDYA_NO_AUTOLOAD"):
        from .config import PREFERRED_DATASET
        files = sorted(RAW_DIR.glob("*.csv"))
        chosen, why = None, ""
        if (RAW_DIR / PREFERRED_DATASET).exists():
            chosen, why = RAW_DIR / PREFERRED_DATASET, "configured dataset"
        elif len(files) == 1:
            chosen, why = files[0], "the only CSV in data/raw"
        if chosen:
            threading.Thread(target=STORE.load, args=(chosen,), daemon=True).start()
            print(f"[abhedya] ingesting {chosen.name} in the background ({why})")
        elif files:
            # Several candidates and none of them named: guessing here would
            # quietly run the demo on the wrong dataset.
            print(f"[abhedya] {len(files)} CSVs in data/raw and none is "
                  f"'{PREFERRED_DATASET}' - refusing to guess. "
                  f"Choose one with POST /api/ingest {{\"filename\": ...}} or set "
                  f"ABHEDYA_DATASET. Available: "
                  + ", ".join(p.name for p in files))
        else:
            print("[abhedya] no CSV in data/raw - waiting for POST /api/ingest")
    yield


app = FastAPI(title="ABHEDYA-CHAKRA API", version=API_VERSION,
              default_response_class=FastJSON, docs_url="/api/docs",
              openapi_url="/api/openapi.json", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.middleware("http")
async def envelope_mw(request: Request, call_next):
    request.state.request_id = new_request_id()
    started = time.perf_counter()
    try:
        resp = await call_next(request)
    except ApiError as e:
        return fail(request, started, e)
    except Exception as e:                                   # noqa: BLE001
        return fail(request, started,
                    ApiError("INTERNAL_ERROR", "Unhandled server error.",
                             detail={"type": type(e).__name__, "message": str(e)[:300]}))
    resp.headers["X-Request-Id"] = request.state.request_id
    resp.headers["X-Processing-Ms"] = f"{(time.perf_counter() - started) * 1000:.2f}"
    return resp


@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError):
    return fail(request, time.perf_counter(), exc)


app.include_router(router)
app.include_router(compat_router)


