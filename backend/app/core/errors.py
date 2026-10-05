"""Consistent error envelope for the whole API.

Every error response has the shape:
    {"error": {"code": "SOME_CODE", "message": "Human readable", "details": {...}}}

Raw Python / database exceptions are never sent to the client.
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, *, code: str | None = None, details: Any = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.details = details


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class PermissionDenied(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"


class NotAuthenticated(AppError):
    status_code = 401
    code = "NOT_AUTHENTICATED"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class BusinessRuleViolation(AppError):
    status_code = 422
    code = "BUSINESS_RULE"


def _envelope(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_envelope(exc.code, exc.message, exc.details))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "NOT_AUTHENTICATED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_envelope(code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope("VALIDATION_ERROR", "Some fields are missing or invalid.", {"fields": fields}),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_: Request, exc: IntegrityError):
        log.warning("Integrity error: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content=_envelope("DATA_CONFLICT", "This change conflicts with existing records. Refresh and try again."),
        )

    @app.exception_handler(OperationalError)
    async def _db_unavailable(_: Request, exc: OperationalError):
        log.error("Database operational error: %s", exc.orig)
        return JSONResponse(
            status_code=503,
            content=_envelope("DATABASE_UNAVAILABLE", "The database is temporarily unavailable. Please try again shortly."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error")
        return JSONResponse(
            status_code=500,
            content=_envelope("INTERNAL_ERROR", "Something went wrong on our side. The error has been logged."),
        )
