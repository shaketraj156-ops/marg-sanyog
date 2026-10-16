from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="Block planner API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
