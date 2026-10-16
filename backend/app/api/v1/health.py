from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness only: does not touch the database or Redis."""
    return {"status": "ok"}
