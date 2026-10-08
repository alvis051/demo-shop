"""Shared helpers for routes: templates, flash messages, redirects."""

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.cart import cart_count, money
from app.models import User

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.filters["money"] = money


def flash(request: Request, message: str, level: str = "info") -> None:
    request.session.setdefault("flash", []).append([level, message])


def _session_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    with request.app.state.db.sessions() as db:
        return db.get(User, user_id)


def render(request: Request, name: str, status_code: int = 200, **context):
    if "user" not in context:
        context["user"] = _session_user(request)
    context.update(
        flashes=request.session.pop("flash", []),
        cart_count=cart_count(request.session),
        settings=request.app.state.settings,
    )
    return templates.TemplateResponse(request, name, context, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)
