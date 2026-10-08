import asyncio
from contextlib import asynccontextmanager
from http import HTTPStatus
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.auth import LoginRequired
from app.config import Settings, get_settings
from app.db import Database
from app.faults import Faults
from app.routes import admin, auth, cart, catalog, checkout, orders
from app.seed import seed
from app.web import redirect, render

ERROR_TITLES = {
    403: "You don't have access to this page",
    404: "Page not found",
    405: "Method not allowed",
    503: "Service temporarily unavailable",
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database(settings)
        if db.schema:
            db.create_schema()
            with db.sessions() as session:
                seed(session, settings)
        app.state.db = db
        if message := getattr(app.state, "ready_message", None):
            print(message, flush=True)
        try:
            yield
        finally:
            db.close()

    app = FastAPI(title="demo-shop", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.faults = Faults.from_settings(settings)

    @app.middleware("http")
    async def latency_and_headers(request: Request, call_next):
        faults: Faults = request.app.state.faults
        if faults.allowed and faults.latency_ms and request.url.path != "/healthz":
            await asyncio.sleep(faults.latency_ms / 1000)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if settings.is_prod:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="demo_shop_session",
        same_site="lax",
        https_only=settings.secure_cookies,
    )

    @app.exception_handler(LoginRequired)
    async def login_required(request: Request, exc: LoginRequired):
        return redirect(f"/login?next={quote(exc.next_url)}")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        title = ERROR_TITLES.get(exc.status_code, "Something went wrong")
        default = HTTPStatus(exc.status_code).phrase
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail != default else None
        return render(request, "error.html", exc.status_code, title=title, detail=detail)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        detail = "Some of what you sent wasn't valid. Go back, check the form and try again."
        return render(request, "error.html", 400, title="Bad request", detail=detail)

    @app.get("/healthz", include_in_schema=False)
    def healthz(request: Request):
        with request.app.state.db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return PlainTextResponse(f"ok {settings.version}")

    app.mount("/static", StaticFiles(directory=__file__.rsplit("/", 1)[0] + "/static"), name="static")
    for module in (catalog, auth, cart, checkout, orders, admin):
        app.include_router(module.router)
    return app
