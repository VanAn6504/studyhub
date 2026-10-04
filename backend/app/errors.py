import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException

logger = logging.getLogger("studyhub")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(request: Request, status: int, code: str, message: str, details: dict | None = None):
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}, "request_id": request.state.request_id},
        headers={"X-Request-ID": request.state.request_id},
    )


def register_error_handlers(app):
    @app.exception_handler(ApiError)
    async def handle_api(request: Request, exc: ApiError):
        return error_response(request, exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, exc: RequestValidationError):
        # Pydantic's raw errors include submitted input (including passwords).
        issues = [{"location": list(error["loc"]), "type": error["type"], "message": "Trường dữ liệu không hợp lệ."} for error in exc.errors()]
        return error_response(request, 422, "VALIDATION_ERROR", "Dữ liệu gửi lên không hợp lệ.", {"issues": issues})

    @app.exception_handler(HTTPException)
    async def handle_http(request: Request, exc: HTTPException):
        messages = {404: "Không tìm thấy tài nguyên.", 405: "Phương thức không được hỗ trợ."}
        return error_response(request, exc.status_code, "HTTP_ERROR", messages.get(exc.status_code, "Yêu cầu không hợp lệ."))

    @app.exception_handler(IntegrityError)
    async def handle_integrity(request: Request, exc: IntegrityError):
        return error_response(request, 409, "RESOURCE_CONFLICT", "Dữ liệu bị trùng hoặc xung đột với trạng thái hiện tại.")

    @app.exception_handler(SQLAlchemyError)
    async def handle_database(request: Request, exc: SQLAlchemyError):
        logger.error("Database unavailable; request_id=%s", request.state.request_id)
        return error_response(request, 503, "DATABASE_UNAVAILABLE", "Cơ sở dữ liệu chưa sẵn sàng.")

    @app.exception_handler(Exception)
    async def handle_unknown(request: Request, exc: Exception):
        logger.error("Internal error type=%s request_id=%s", type(exc).__name__, request.state.request_id)
        return error_response(request, 500, "INTERNAL_ERROR", "Đã xảy ra lỗi xử lý yêu cầu.")
