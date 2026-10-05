from uuid import uuid4

from fastapi import FastAPI, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import activity, auth, courses, paths, predictions, quizzes, resources
from app.config import get_settings
from app.db import get_engine
from app.errors import ApiError, error_response, register_error_handlers
from app.security import UNSAFE_METHODS
from app.upload_limit import RequestBodyLimit

VERSION = "0.3.0"


def create_app() -> FastAPI:
    # Fail before accepting requests if mandatory configuration is missing.
    settings = get_settings()
    application = FastAPI(title="StudyHub API", version=VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    register_error_handlers(application)

    @application.middleware("http")
    async def request_boundary(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if request.method in UNSAFE_METHODS and request.headers.get("origin") not in settings.origin_set:
            return error_response(request, 403, "ORIGIN_FORBIDDEN", "Nguồn gửi yêu cầu không được phép.")
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @application.get("/api/v1/health", tags=["health"])
    def health():
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise ApiError(503, "DATABASE_UNAVAILABLE", "Cơ sở dữ liệu chưa sẵn sàng.", {"status": "unavailable", "service": "studyhub-api", "version": VERSION})
        return {"status": "ok", "service": "studyhub-api", "version": VERSION}

    application.include_router(auth.router, prefix="/api/v1")
    application.include_router(courses.router, prefix="/api/v1")
    application.include_router(resources.router, prefix="/api/v1")
    application.include_router(quizzes.router, prefix="/api/v1")
    application.include_router(activity.router, prefix="/api/v1")
    application.include_router(paths.router, prefix="/api/v1")
    application.include_router(predictions.router, prefix="/api/v1")
    application.add_middleware(RequestBodyLimit)
    return application


app = create_app()
