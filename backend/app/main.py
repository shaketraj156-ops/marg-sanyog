import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, health, me, plans, reference, requests, traffic
from app.config import get_settings
from app.core.errors import install_handlers
from app.services import plan_service

settings = get_settings()

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(me.router)
api_v1.include_router(reference.router)
api_v1.include_router(requests.router)
api_v1.include_router(plans.router)
api_v1.include_router(traffic.router)
app.include_router(api_v1)
