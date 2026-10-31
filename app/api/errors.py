from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain import errors

# HTTP lives here, not in the domain: the same rules also run in workers with no HTTP at all
STATUS_BY_ERROR: dict[type[errors.DomainError], int] = {
    errors.NotFound: status.HTTP_404_NOT_FOUND,
    errors.InvalidAmount: status.HTTP_422_UNPROCESSABLE_CONTENT,
    errors.InsufficientFunds: status.HTTP_422_UNPROCESSABLE_CONTENT,
    errors.SelfTransfer: status.HTTP_422_UNPROCESSABLE_CONTENT,
    errors.IdempotencyConflict: status.HTTP_422_UNPROCESSABLE_CONTENT,
    errors.InvalidTransition: status.HTTP_409_CONFLICT,
    errors.EmailTaken: status.HTTP_409_CONFLICT,
    errors.InvalidCredentials: status.HTTP_401_UNAUTHORIZED,
    errors.InvalidSignature: status.HTTP_401_UNAUTHORIZED,
    errors.PermissionDenied: status.HTTP_403_FORBIDDEN,
}


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, errors.DomainError)
    code = STATUS_BY_ERROR.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(error_body(exc.code, exc.message), status_code=code)


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"][1:])
    message = f"{field}: {first['msg']}" if field else first["msg"]
    return JSONResponse(
        error_body("validation_error", message),
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(errors.DomainError, handle_domain_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
