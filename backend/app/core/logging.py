"""JSON logs with a request id. Bodies, passwords and tokens are never logged."""
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

FIELDS = ("request_id", "method", "path", "status", "duration_ms", "user_id", "client")
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

access_log = logging.getLogger("access")


class JsonFormatter(logging.Formatter):
    """One JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                data[field] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """Send every log line to stderr as JSON. Safe to call more than once."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.set_name("json")
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if h.get_name() != "json"] + [handler]
    root.setLevel(level.upper())
    # The access logger below replaces uvicorn's plain-text access lines.
    logging.getLogger("uvicorn.access").disabled = True


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def request_id_of(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Gives every request an id (or keeps a safe one sent by the caller), echoes it in the
    X-Request-ID header and writes one JSON line per request."""

    async def dispatch(self, request: Request, call_next):
        sent = request.headers.get("x-request-id", "")
        request.state.request_id = sent if SAFE_ID.match(sent) else new_request_id()
        request.state.user_id = None
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            access_log.exception(
                "unhandled error",
                extra=self._fields(request, 500, started),
            )
            raise
        response.headers["X-Request-ID"] = request.state.request_id
        access_log.info("request", extra=self._fields(request, response.status_code, started))
        return response

    @staticmethod
    def _fields(request: Request, status: int, started: float) -> dict:
        return {
            "request_id": request.state.request_id,
            "method": request.method,
            "path": request.url.path,  # the path only: query strings can carry filters, not secrets
            "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "user_id": request.state.user_id,
            "client": request.client.host if request.client else None,
        }
