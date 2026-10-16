from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


class ProblemError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        headers: dict[str, str] | None = None,
        extra: dict | None = None,
    ):
        super().__init__(detail)
        self.status, self.code, self.detail, self.headers = status, code, detail, headers
        self.extra = extra or {}


def problem(
    status: int, code: str, detail: str, headers: dict[str, str] | None = None, **extra
) -> JSONResponse:
    body = {
        "type": f"/problems/{code}",
        "title": code,
        "status": status,
        "detail": detail,
        **extra,
    }
    return JSONResponse(
        body, status_code=status, media_type="application/problem+json", headers=headers
    )


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def on_problem(_: Request, exc: ProblemError):
        return problem(exc.status, exc.code, exc.detail, exc.headers, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def on_validation(_: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(p) for p in e["loc"][1:]) or "(whole request)",
                "message": e["msg"],
            }
            for e in exc.errors()
        ]
        return problem(422, "validation", "Request body is invalid", errors=errors)

    @app.exception_handler(Exception)
    async def on_unhandled(request: Request, _: Exception):
        request_id = getattr(request.state, "request_id", None)
        extra = {"request_id": request_id} if request_id else {}
        headers = {"X-Request-ID": request_id} if request_id else None
        return problem(
            500,
            "internal_error",
            "Something went wrong on the server. Quote the request id when you report it.",
            headers,
            **extra,
        )

    @app.exception_handler(StarletteHTTPException)
    async def on_http(_: Request, exc: StarletteHTTPException):
        code = HTTP_CODES.get(exc.status_code, "http_error")
        return problem(exc.status_code, code, str(exc.detail), exc.headers)
