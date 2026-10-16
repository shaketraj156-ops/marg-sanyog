import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, blocks, health, me, ml, plans, reference, requests, traffic
from app.config import get_settings
from app.core.errors import install_handlers
from app.core.logging import RequestLogMiddleware, setup_logging
from app.services import plan_service

settings = get_settings()
setup_logging(settings.log_level)

# The Vite dev server for the frontend, always allowed in addition to CORS_ORIGINS.
DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A run that was queued or running when the server stopped can never finish.
    from app.db.session import get_session

    try:
        with get_session() as db:
            stopped = plan_service.fail_orphaned_runs(db)
        if stopped:
            log.warning("marked %s unfinished plan runs as failed", stopped)
    except Exception:
        log.warning("could not check for unfinished plan runs", exc_info=True)
    yield


app = FastAPI(title="Block planner API", lifespan=lifespan)
install_handlers(app)

app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted({*settings.cors_origins, *DEV_ORIGINS}),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)

app.include_router(health.router)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(me.router)
api_v1.include_router(reference.router)
api_v1.include_router(requests.router)
api_v1.include_router(plans.router)
api_v1.include_router(traffic.router)
api_v1.include_router(blocks.router)
api_v1.include_router(ml.router)
app.include_router(api_v1)
